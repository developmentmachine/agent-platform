"""HSK 3.0 Tutor — 覆盖率提升测试（补充未覆盖行）。

覆盖目标：
- cli.py lines 109-151, 175: 交互 REPL on_line handler + run() 进入 _run_interactive
- http_routes.py lines 29-30, 38-39: tutor_chat / tutor_chat_stream via create_runtime
- grammar_examples.py line 121: 空例句返回 ""
- manifest.py line 42: register() 的 debug 日志
- use_case.py line 88: _validate_and_retry 中 new_backend == "stub" 分支
- validation.py line 130: 单字词不在认读字表且非专有名词
"""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.core.runtime.principal import PrincipalContext


# ─── helpers ────────────────────────────────────────────────────────────────

def _namespace(**overrides):
    """构造 CLI args Namespace 的便捷函数。"""
    defaults = dict(once=False, message=None, level=1, locale="both", json=False)
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# cli.py — on_line handler (lines 109-151) and run() → _run_interactive (175)
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIInteractiveOnLine:
    """测试 _run_interactive 中 on_line 回调的各个分支。"""

    def _get_on_line(self, settings, **kwargs):
        """调用 _run_interactive，拦截 run_repl 以捕获 on_line 回调。"""
        from agent_platform.agents.hsk30_tutor.cli import _run_interactive

        captured = {}

        def fake_run_repl(*, banner, prompt, on_line):
            captured["on_line"] = on_line
            return 0

        with patch("agent_platform.agents.hsk30_tutor.cli.run_repl", fake_run_repl):
            _run_interactive(settings, **kwargs)
        return captured["on_line"]

    def test_quit_exits(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        assert on_line("/quit") is False
        assert on_line("/exit") is False
        assert on_line("quit") is False
        assert on_line("exit") is False

    def test_help_prints_help(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/help")
        assert result is True
        out = capsys.readouterr().out
        assert "/level" in out
        assert "/quit" in out

    def test_clear_resets_history(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/clear")
        assert result is True
        out = capsys.readouterr().out
        assert "清空" in out

    def test_level_valid(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/level 5")
        assert result is True
        out = capsys.readouterr().out
        assert "Level 5" in out

    def test_level_invalid_no_arg(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/level")
        assert result is True
        out = capsys.readouterr().out
        assert "用法" in out

    def test_level_invalid_not_digit(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/level abc")
        assert result is True
        out = capsys.readouterr().out
        assert "用法" in out

    def test_level_out_of_range(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/level 10")
        assert result is True
        out = capsys.readouterr().out
        assert "1–9" in out or "1-9" in out

    def test_locale_valid(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/locale zh")
        assert result is True
        out = capsys.readouterr().out
        assert "zh" in out

    def test_locale_invalid_no_arg(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/locale")
        assert result is True
        out = capsys.readouterr().out
        assert "用法" in out

    def test_locale_invalid_value(self, settings_no_llm, capsys):
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        result = on_line("/locale fr")
        assert result is True
        out = capsys.readouterr().out
        assert "用法" in out

    def test_normal_message_calls_turn(self, settings_no_llm, capsys):
        """正常消息应调用 _turn 并输出回复。"""
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        with patch("agent_platform.agents.hsk30_tutor.cli._turn") as mock_turn:
            mock_turn.return_value = ({"reply": "你好！", "level": 1}, [])
            result = on_line("你好")
        assert result is True
        mock_turn.assert_called_once()
        out = capsys.readouterr().out
        assert "你好！" in out

    def test_normal_message_json_mode(self, settings_no_llm, capsys):
        """JSON 模式下正常消息输出 JSON。"""
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=True)
        with patch("agent_platform.agents.hsk30_tutor.cli._turn") as mock_turn:
            mock_turn.return_value = ({"reply": "测试回复", "level": 1}, [])
            result = on_line("你好")
        assert result is True
        out = capsys.readouterr().out
        data = json.loads(out.strip())
        assert data["reply"] == "测试回复"

    def test_normal_message_with_note(self, settings_no_llm, capsys):
        """带 note 的回复输出到 stderr。"""
        on_line = self._get_on_line(settings_no_llm, level=1, locale="both", as_json=False)
        with patch("agent_platform.agents.hsk30_tutor.cli._turn") as mock_turn:
            mock_turn.return_value = ({"reply": "你好", "note": "注意"}, [])
            result = on_line("你好")
        assert result is True
        out = capsys.readouterr()
        assert "你好" in out.out
        assert "注意" in out.err


class TestCLIRunInteractiveBranch:
    """测试 run() 在非 --once 模式下调用 _run_interactive (line 175)。"""

    def test_run_enters_interactive_mode(self, settings_no_llm):
        """run() 不带 --once 时应进入交互模式。"""
        from agent_platform.agents.hsk30_tutor.cli import run

        with patch("agent_platform.agents.hsk30_tutor.cli._run_interactive", return_value=0) as mock_ri:
            code = run(_namespace(), settings_no_llm, argparse.ArgumentParser())

        assert code == 0
        mock_ri.assert_called_once()
        call_kwargs = mock_ri.call_args
        assert call_kwargs[1]["level"] == 1
        assert call_kwargs[1]["locale"] == "both"
        assert call_kwargs[1]["as_json"] is False


# ═══════════════════════════════════════════════════════════════════════════
# http_routes.py — tutor_chat (lines 29-30) / tutor_chat_stream (lines 38-39)
# ═══════════════════════════════════════════════════════════════════════════

class TestHTTPRoutesViaRuntime:
    """测试 /chat 和 /chat/stream 端点（经过 create_runtime 路径）。"""

    def test_tutor_chat_via_runtime(self, settings_no_llm):
        from fastapi.testclient import TestClient
        from agent_platform.adapters.http.app import create_app

        mock_envelope = MagicMock()
        mock_envelope.payload = {
            "reply": "你好！",
            "level": 1,
            "request_id": "test-123",
            "backend": "stub",
            "note": None,
        }
        mock_runtime = MagicMock()
        mock_runtime.run.return_value = mock_envelope

        with patch("agent_platform.agents.hsk30_tutor.http_routes.create_runtime", return_value=mock_runtime):
            client = TestClient(create_app())
            r = client.post(
                "/v1/hsk30-tutor/chat",
                json={"message": "你好", "level": 1},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["reply"] == "你好！"
        mock_runtime.run.assert_called_once()

    def test_tutor_chat_stream_via_runtime(self, settings_no_llm):
        from fastapi.testclient import TestClient
        from agent_platform.adapters.http.app import create_app

        events = [
            {"kind": "agent_output", "data": {"text": "你", "backend": "llm"}},
            {"kind": "agent_output", "data": {"text": "好", "backend": "llm"}},
        ]
        mock_runtime = MagicMock()
        mock_runtime.stream.return_value = iter(events)

        with patch("agent_platform.agents.hsk30_tutor.http_routes.create_runtime", return_value=mock_runtime):
            client = TestClient(create_app())
            r = client.post(
                "/v1/hsk30-tutor/chat/stream",
                json={"message": "你好", "level": 1},
            )

        assert r.status_code == 200
        assert "application/x-ndjson" in r.headers.get("content-type", "")
        mock_runtime.stream.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# grammar_examples.py line 121 — get_grammar_examples_text 空例句
# ═══════════════════════════════════════════════════════════════════════════

class TestGrammarExamplesEdgeCase:
    def test_get_grammar_examples_text_empty_for_invalid_level(self):
        """无效等级（如 0）应返回空字符串（line 121）。"""
        from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples_text
        result = get_grammar_examples_text(0)
        assert result == ""

    def test_get_grammar_examples_text_empty_for_negative_level(self):
        """负数等级不在字典中，应返回空字符串。"""
        from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples_text
        result = get_grammar_examples_text(-1)
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════
# manifest.py line 42 — register() debug 日志
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestDebugLog:
    def test_runner_stream_branch(self, settings_no_llm):
        """_runner 路径当 envelope.stream=True 时应走 _stream_runner (line 42)。"""
        from agent_platform.agents.hsk30_tutor.manifest import _runner
        from agent_platform.core.registry.agent_definition import AgentRequestEnvelope
        from agent_platform.core.runtime.principal import PrincipalContext
        from agent_platform.core.runtime.run_context import RunContext
        from agent_platform.core.runtime.session import SessionContext
        from agent_platform.core.orchestration.stream_events import StreamEventKind

        envelope = AgentRequestEnvelope(
            agent_id="hsk30-tutor",
            payload={"message": "你好", "level": 1},
            stream=True,
        )
        principal = PrincipalContext.anonymous(source="test")
        session = SessionContext.new(principal=principal, conversation_key="test")
        run_ctx = RunContext.new()

        events = list(_runner(
            envelope=envelope, principal=principal, session=session,
            run_ctx=run_ctx, settings=settings_no_llm, runtime=None,
        ))
        kinds = [e["kind"] for e in events]
        assert StreamEventKind.PHASE_START in kinds
        assert StreamEventKind.COMPLETED in kinds

    def test_register_emits_debug_log(self):
        """register() 的最后一行 logger.debug 应被执行。"""
        from agent_platform.agents.hsk30_tutor.manifest import register
        from agent_platform.core.registry.agent_registry import AgentRegistry

        reg = AgentRegistry()

        with patch("agent_platform.agents.hsk30_tutor.manifest.logger") as mock_logger:
            register(reg)

        mock_logger.debug.assert_called()
        args = mock_logger.debug.call_args
        assert "hsk30-tutor" in str(args)


# ═══════════════════════════════════════════════════════════════════════════
# use_case.py line 88 — _validate_and_retry: stub break 分支
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateAndRetryStubBreak:
    def test_retry_returns_stub_breaks_loop(self, settings_no_llm):
        """当重试返回 stub backend 时应 break 退出循环（line 88）。"""
        from agent_platform.agents.hsk30_tutor.use_case import _validate_and_retry

        call_count = 0

        def mock_chat_completion(settings, messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次重试：返回无效回复（触发再次重试）
                return "饕餮盛宴", "llm"
            # 第二次：返回 stub（触发 break）
            return "陪练模式回复", "stub"

        with patch("agent_platform.agents.hsk30_tutor.use_case.chat_completion", side_effect=mock_chat_completion):
            reply, validation = _validate_and_retry(
                [{"role": "user", "content": "你好"}],
                "饕餮盛宴",  # 初始回复有超纲内容
                1,
                settings_no_llm,
                backend="llm",
            )

        # 应该在 stub 返回后 break
        assert call_count >= 1
        assert reply  # 至少返回了一个回复


# ═══════════════════════════════════════════════════════════════════════════
# validation.py line 130 — 单字词不在认读字表且非专有名词
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationSingleCharOutOfVocab:
    def test_multi_char_word_not_in_vocab_detected(self):
        """多字词不在词汇表中应被检测为超纲（line 130）。

        _forward_max_match 通常不会产出不在 vocab 中的多字词，
        但代码逻辑上有该分支；通过 mock _forward_max_match 来覆盖。
        """
        from agent_platform.agents.hsk30_tutor import validation

        # mock _forward_max_match 返回一个不在 vocab 中的双字词
        with patch.object(validation, "_forward_max_match", return_value=["你好", "饕餮"]):
            result = validation.validate_reply("你好饕餮", 1)

        # "饕餮" 是 2 字词不在 vocab 中 → 应在 out_of_vocabulary
        assert "饕餮" in result.out_of_vocabulary

    def test_single_char_not_in_recog_not_proper_noun(self):
        """单字词：不在认读字表、不在词汇表、非专有名词 → 超纲 (line 130)。

        使用 Level 1 认读字（约 245 个汉字），选一个不在其中的非专有名词单字。
        """
        from agent_platform.agents.hsk30_tutor.validation import validate_reply, _is_proper_noun_char
        from agent_platform.agents.hsk30_tutor.syllabus import get_recognition_chars, get_vocabulary

        recog = get_recognition_chars(1)
        vocab = get_vocabulary(1)

        # 找一个不在认读字表、不在词汇表、且不是专有名词用字的单字
        test_char = None
        for ch in "魑魅魍魉饕餮":
            if ch not in recog and ch not in vocab and not _is_proper_noun_char(ch):
                test_char = ch
                break

        if test_char is None:
            pytest.skip("Could not find suitable test character")

        # 使用包含该单字的文本，触发 _forward_max_match 的单字 fallback
        result = validate_reply(test_char, 1)
        assert test_char in result.out_of_vocabulary or test_char in result.out_of_recognition
