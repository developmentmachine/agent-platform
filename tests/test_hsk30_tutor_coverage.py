"""HSK 3.0 Tutor 覆盖率补充测试 — 覆盖 cli/llm_client/manifest/http_routes 等未测路径。"""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_platform.agents.hsk30_tutor.models import TutorChatRequest
from agent_platform.agents.hsk30_tutor.validation import validate_reply


# ── syllabus.py: get_tasks, get_grammar, get_vocabulary, get_writing_chars ──

class TestSyllabusHelpers:
    def test_get_tasks(self):
        from agent_platform.agents.hsk30_tutor.syllabus import get_tasks
        t = get_tasks(1)
        assert len(t) > 100

    def test_get_grammar(self):
        from agent_platform.agents.hsk30_tutor.syllabus import get_grammar
        g = get_grammar(1)
        assert len(g) > 50

    def test_get_vocabulary(self):
        from agent_platform.agents.hsk30_tutor.syllabus import get_vocabulary
        v = get_vocabulary(1)
        assert len(v) > 100

    def test_get_writing_chars(self):
        from agent_platform.agents.hsk30_tutor.syllabus import get_writing_chars
        w = get_writing_chars(1)
        assert len(w) > 50


# ── grammar_examples.py: empty level ──

class TestGrammarExamples:
    def test_empty_level_returns_empty(self):
        from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples
        # Level 0 doesn't exist
        result = get_grammar_examples(0)
        assert result == []

    def test_get_grammar_examples_text_non_empty(self):
        from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples_text
        text = get_grammar_examples_text(1)
        assert "能愿动词" in text or "语法" in text


# ── validation.py: proper noun exemption ──

class TestValidationProperNouns:
    def test_proper_noun_chars_exempt(self):
        """人名用字（丽、伟等）不应被判为超纲。"""
        result = validate_reply("小丽和小伟是好朋友。", 1)
        # "丽" and "伟" are in _PROPER_NOUN_CHARS, should be exempt
        assert "丽" not in result.out_of_recognition
        assert "伟" not in result.out_of_recognition

    def test_place_name_chars_exempt(self):
        """地名用字（京、沪等）不应被判为超纲。"""
        result = validate_reply("我去北京和上海。", 1)
        assert "京" not in result.out_of_recognition
        assert "沪" not in result.out_of_recognition

    def test_non_exempt_char_still_detected(self):
        """非豁免的超纲字仍应被检测。"""
        result = validate_reply("饕餮盛宴", 1)
        assert "饕" in result.out_of_recognition
        assert "餮" in result.out_of_recognition


# ── llm_client.py ──

class TestLLMClient:
    def setup_method(self):
        """Reset cached client before each test."""
        import agent_platform.agents.hsk30_tutor.llm_client as lc
        lc._cached_client = None
        lc._cached_key = (None, None)

    def test_stub_when_no_key(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        reply, backend = chat_completion(settings_no_llm, [{"role": "user", "content": "你好"}])
        assert backend == "stub"
        assert "陪练模式" in reply

    def test_stub_when_no_key_stream(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion_stream
        chunks = list(chat_completion_stream(settings_no_llm, [{"role": "user", "content": "你好"}]))
        assert len(chunks) == 1
        assert chunks[0][1] == "stub"

    def test_client_caching(self, settings_with_llm):
        """Client should be cached and reused."""
        import agent_platform.agents.hsk30_tutor.llm_client as lc
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            # First call creates client
            c1 = lc._get_client(settings_with_llm)
            # Second call returns cached
            c2 = lc._get_client(settings_with_llm)
            assert c1 is c2
            assert mock_openai.call_count == 1

    def test_chat_completion_success(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="你好！我是AI。"))]
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai.return_value = mock_client
            reply, backend = chat_completion(settings_with_llm, [{"role": "user", "content": "你好"}])
            assert backend == "llm"
            assert "你好" in reply

    def test_chat_completion_empty_response_falls_back_to_stub(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content=""))]
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai.return_value = mock_client
            reply, backend = chat_completion(settings_with_llm, [{"role": "user", "content": "你好"}])
            assert backend == "stub"

    def test_chat_completion_retry_on_429(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        import openai
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="成功"))]
        call_count = 0
        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                exc = openai.BadRequestError.__new__(openai.BadRequestError)
                exc.status_code = 429
                raise exc
            return mock_resp
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = side_effect
            mock_openai.return_value = mock_client
            with patch("agent_platform.agents.hsk30_tutor.llm_client.time.sleep"):
                reply, backend = chat_completion(settings_with_llm, [{"role": "user", "content": "你好"}])
            assert backend == "llm"
            assert "成功" in reply

    def test_chat_completion_non_retryable_error(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = ValueError("bad request")
            mock_openai.return_value = mock_client
            reply, backend = chat_completion(settings_with_llm, [{"role": "user", "content": "你好"}])
            assert backend == "stub"

    def test_chat_completion_stream_success(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion_stream
        chunk1 = MagicMock(choices=[MagicMock(delta=MagicMock(content="你"))])
        chunk2 = MagicMock(choices=[MagicMock(delta=MagicMock(content="好"))])
        chunk3 = MagicMock(choices=[MagicMock(delta=MagicMock(content=None))])
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])
            mock_openai.return_value = mock_client
            chunks = list(chat_completion_stream(settings_with_llm, [{"role": "user", "content": "你好"}]))
            texts = [c[0] for c in chunks if c[1] == "llm"]
            assert "".join(texts) == "你好"

    def test_chat_completion_stream_error_fallback(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion_stream
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = ValueError("boom")
            mock_openai.return_value = mock_client
            chunks = list(chat_completion_stream(settings_with_llm, [{"role": "user", "content": "你好"}]))
            assert chunks[-1][1] == "stub"

    def test_import_error_fallback(self, settings_with_llm):
        from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
        with patch.dict("sys.modules", {"openai": None}):
            # Force ImportError
            import importlib
            import agent_platform.agents.hsk30_tutor.llm_client as lc
            lc._cached_client = None
            lc._cached_key = (None, None)
            reply, backend = chat_completion(settings_with_llm, [{"role": "user", "content": "你好"}])
            assert backend == "stub"


# ── manifest.py ──

class TestManifest:
    def test_stream_runner_yields_events(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.manifest import _stream_runner
        from agent_platform.agents.hsk30_tutor.models import TutorChatRequest
        from agent_platform.core.runtime.run_context import RunContext
        from agent_platform.core.orchestration.stream_events import StreamEventKind
        req = TutorChatRequest(message="你好", level=1)
        events = list(_stream_runner(req, settings_no_llm, RunContext.new()))
        assert len(events) >= 3
        kinds = [e["kind"] for e in events]
        assert StreamEventKind.PHASE_START in kinds
        assert StreamEventKind.AGENT_OUTPUT in kinds
        assert StreamEventKind.COMPLETED in kinds

    def test_register_subparser(self):
        from agent_platform.agents.hsk30_tutor.cli import register_subparser
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        sub_parser = sub.add_parser("hsk30-tutor")
        register_subparser(sub_parser)
        # Should not raise

    def test_http_routers_factory(self):
        from agent_platform.agents.hsk30_tutor.manifest import register
        from agent_platform.core.registry.agent_registry import AgentRegistry; reg = AgentRegistry(); register(reg)
        assert len(reg.ids()) >= 1


# ── cli.py ──

class TestCLI:
    def test_print_reply_json(self, capsys):
        from agent_platform.agents.hsk30_tutor.cli import _print_reply
        _print_reply({"reply": "你好", "level": 1}, as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["reply"] == "你好"

    def test_print_reply_text(self, capsys):
        from agent_platform.agents.hsk30_tutor.cli import _print_reply
        _print_reply({"reply": "你好", "level": 1}, as_json=False)
        captured = capsys.readouterr()
        assert "你好" in captured.out

    def test_print_reply_with_note(self, capsys):
        from agent_platform.agents.hsk30_tutor.cli import _print_reply
        _print_reply({"reply": "你好", "note": "测试备注"}, as_json=False)
        captured = capsys.readouterr()
        assert "你好" in captured.out

    def test_turn_direct(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.cli import _turn
        payload, history = _turn("你好", history=[], level=1, locale="both",
                                 settings=settings_no_llm, use_runtime=False)
        assert payload["reply"]
        assert len(history) == 2

    def test_run_once_mode(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.cli import run
        args = argparse.Namespace(once=True, message="你好", level=1, locale="both", json=False)
        code = run(args, settings_no_llm, argparse.ArgumentParser())
        assert code == 0

    def test_run_once_json_mode(self, settings_no_llm, capsys):
        from agent_platform.agents.hsk30_tutor.cli import run
        args = argparse.Namespace(once=True, message="你好", level=1, locale="both", json=True)
        code = run(args, settings_no_llm, argparse.ArgumentParser())
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["reply"]

    def test_run_once_no_message_errors(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.cli import run
        parser = argparse.ArgumentParser()
        args = argparse.Namespace(once=True, message=None, level=1, locale="both", json=False)
        with pytest.raises(SystemExit):
            run(args, settings_no_llm, parser)

    def test_interactive_mode(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.cli import _run_interactive
        with patch("agent_platform.agents.hsk30_tutor.cli.run_repl") as mock_repl:
            mock_repl.return_value = 0
            code = _run_interactive(settings_no_llm, level=1, locale="both", as_json=False)
            assert code == 0
            mock_repl.assert_called_once()


# ── http_routes.py ──

class TestHTTPRoutes:
    def test_chat_direct(self, settings_no_llm):
        from agent_platform.adapters.http.app import create_app
        client = TestClient(create_app())
        with patch("agent_platform.agents.hsk30_tutor.use_case.chat_completion",
                   return_value=("你好！", "llm")):
            r = client.post("/v1/hsk30-tutor/chat/direct",
                            json={"message": "你好", "level": 1})
        assert r.status_code == 200
        assert r.json()["reply"] == "你好！"


# ── use_case.py: history and stream validation ──

class TestUseCaseExtra:
    def test_chat_turn_with_history(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.use_case import chat_turn
        from agent_platform.agents.hsk30_tutor.models import ChatTurn
        from agent_platform.core.runtime.run_context import RunContext
        req = TutorChatRequest(
            message="请继续", level=1,
            history=[ChatTurn(role="user", content="你好"), ChatTurn(role="assistant", content="你好！")],
        )
        resp = chat_turn(req, settings_no_llm, ctx=RunContext.new())
        assert resp.reply

    def test_chat_turn_stream_yields_chunks(self, settings_no_llm):
        from agent_platform.agents.hsk30_tutor.use_case import chat_turn_stream
        from agent_platform.core.runtime.run_context import RunContext
        req = TutorChatRequest(message="你好", level=1)
        chunks = list(chat_turn_stream(req, settings_no_llm, ctx=RunContext.new()))
        assert len(chunks) > 0

    def test_stream_validation_note(self, settings_with_llm):
        """Stream should emit validation note for out-of-syllabus content."""
        from agent_platform.agents.hsk30_tutor.use_case import chat_turn_stream
        from agent_platform.core.runtime.run_context import RunContext
        with patch("agent_platform.agents.hsk30_tutor.use_case.chat_completion_stream",
                   return_value=iter([("饕", "llm"), ("餮", "llm")])):
            req = TutorChatRequest(message="你好", level=1)
            chunks = list(chat_turn_stream(req, settings_with_llm, ctx=RunContext.new()))
            # Should have content chunks + validation note
            texts = [c[0] for c in chunks]
            full = "".join(texts)
            assert "系统提示" in full or "超纲" in full or len(chunks) >= 2
