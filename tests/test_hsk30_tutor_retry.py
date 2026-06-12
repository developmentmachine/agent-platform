"""HSK 3.0 Tutor 重试修正机制测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_platform.agents.hsk30_tutor.models import TutorChatRequest
from agent_platform.agents.hsk30_tutor.use_case import (
    _build_correction_message,
    _validate_and_retry,
    chat_turn,
    chat_turn_stream,
)
from agent_platform.agents.hsk30_tutor.validation import ValidationResult
from agent_platform.core.runtime.run_context import RunContext


class TestBuildCorrectionMessage:
    def test_contains_out_of_recog_chars(self):
        v = ValidationResult(
            level=1, valid=False,
            out_of_recognition=["饕", "餮"], out_of_vocabulary=[],
            total_chinese_chars=10, total_words=5,
            char_coverage_pct=80.0, word_coverage_pct=100.0,
        )
        msg = _build_correction_message(v)
        assert "饕" in msg
        assert "餮" in msg
        assert "超纲认读字" in msg

    def test_contains_out_of_vocab_words(self):
        v = ValidationResult(
            level=1, valid=False,
            out_of_recognition=[], out_of_vocabulary=["人工智能", "影响"],
            total_chinese_chars=10, total_words=5,
            char_coverage_pct=100.0, word_coverage_pct=60.0,
        )
        msg = _build_correction_message(v)
        assert "人工智能" in msg
        assert "影响" in msg
        assert "超纲词汇" in msg

    def test_both_types_present(self):
        v = ValidationResult(
            level=1, valid=False,
            out_of_recognition=["饕"], out_of_vocabulary=["人工智能"],
            total_chinese_chars=10, total_words=5,
            char_coverage_pct=80.0, word_coverage_pct=80.0,
        )
        msg = _build_correction_message(v)
        assert "超纲认读字" in msg
        assert "超纲词汇" in msg


class TestValidateAndRetry:
    def test_valid_reply_no_retry(self, settings_no_llm):
        """验证通过时不应重试。"""
        # 用 Level 7 的认读字（足够多，容易通过）
        with patch(
            "agent_platform.agents.hsk30_tutor.use_case.chat_completion",
            return_value=("你好，我是小明。", "llm"),
        ) as mock_llm:
            reply, v = _validate_and_retry(
                [{"role": "user", "content": "你好"}],
                "你好，我是小明。",
                7,
                settings_no_llm,
            )
            # 不应调用 chat_completion（不需要重试）
            assert mock_llm.call_count == 0
            assert reply == "你好，我是小明。"

    def test_invalid_reply_retries(self, settings_no_llm):
        """验证失败时应重试。"""
        # 第一次回复有超纲内容，重试后回复更好
        better_reply = "你好"
        with patch(
            "agent_platform.agents.hsk30_tutor.use_case.chat_completion",
            return_value=(better_reply, "llm"),
        ) as mock_llm:
            reply, v = _validate_and_retry(
                [{"role": "user", "content": "你好"}],
                "饕餮人工智能",  # 故意用超纲内容
                1,
                settings_no_llm,
            )
            # 应该调用了 chat_completion（重试）
            assert mock_llm.call_count >= 1

    def test_stub_backend_no_retry(self, settings_no_llm):
        """stub 模式不应重试。"""
        with patch(
            "agent_platform.agents.hsk30_tutor.use_case.chat_completion",
            return_value=("stub reply", "stub"),
        ) as mock_llm:
            reply, v = _validate_and_retry(
                [{"role": "user", "content": "你好"}],
                "饕餮",
                1,
                settings_no_llm,
                backend="stub",
            )
            # stub 模式不重试
            assert mock_llm.call_count == 0


class TestChatTurn:
    def test_stub_mode_returns_stub(self, settings_no_llm):
        req = TutorChatRequest(message="你好", level=1)
        resp = chat_turn(req, settings_no_llm, ctx=RunContext.new())
        assert resp.backend == "stub"
        assert resp.note is not None
        assert "OPENAI_API_KEY" in resp.note

    @patch("agent_platform.agents.hsk30_tutor.use_case.chat_completion")
    def test_llm_mode_validates(self, mock_llm, settings_no_llm):
        """LLM 模式应验证回复。"""
        mock_llm.return_value = ("你好，我是小明。", "llm")
        req = TutorChatRequest(message="你好", level=7)
        resp = chat_turn(req, settings_no_llm, ctx=RunContext.new())
        assert resp.backend == "llm"


class TestChatTurnStream:
    def test_stub_mode_yields_stub(self, settings_no_llm):
        req = TutorChatRequest(message="你好", level=1)
        chunks = list(chat_turn_stream(req, settings_no_llm, ctx=RunContext.new()))
        assert len(chunks) > 0
        full_reply = "".join(text for text, _ in chunks)
        assert "陪练模式" in full_reply

    @patch("agent_platform.agents.hsk30_tutor.use_case.chat_completion_stream")
    def test_llm_stream_validates(self, mock_stream, settings_no_llm):
        """LLM 流模式应验证全文。"""
        mock_stream.return_value = iter([("你", "llm"), ("好", "llm")])
        req = TutorChatRequest(message="你好", level=7)
        chunks = list(chat_turn_stream(req, settings_no_llm, ctx=RunContext.new()))
        assert len(chunks) >= 2  # 至少 2 个 chunk
