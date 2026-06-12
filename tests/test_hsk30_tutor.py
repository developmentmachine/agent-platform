"""HSK 3.0 Tutor Agent：注册、对话、与 stock-recap 隔离。"""
from __future__ import annotations

import argparse
import importlib

import pytest
from fastapi.testclient import TestClient

from agent_platform.agents.hsk30_tutor.models import TutorChatRequest
from agent_platform.agents.hsk30_tutor.use_case import chat_turn
from agent_platform.config.settings import Settings
from agent_platform.core.registry.agent_registry import AgentRegistry
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.runtime.factory import create_runtime, register_builtin_agents


@pytest.fixture
def settings_no_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # _env_file=None prevents pydantic-settings from loading .env
    return Settings(_env_file=None, openai_api_key=None, recap_api_key=None)


def test_builtin_registry_has_two_agents():
    reg = AgentRegistry()
    register_builtin_agents(reg)
    ids = sorted(reg.ids())
    assert "stock-recap" in ids
    assert "hsk30-tutor" in ids


def test_chat_turn_stub_without_api_key(settings_no_llm):
    resp = chat_turn(
        TutorChatRequest(message="你好，我是学生。", level=1),
        settings_no_llm,
        ctx=RunContext.new(),
    )
    assert resp.backend == "stub"
    assert "你好" in resp.reply
    assert resp.level == 1
    assert resp.request_id


def test_runtime_run_hsk30_tutor(settings_no_llm):
    runtime = create_runtime(settings_no_llm, register_builtins=True, auto_discover=False)
    out = runtime.run(
        agent_id="hsk30-tutor",
        payload={"message": "请纠正：我昨天去了商店买东西了。", "level": 2},
        principal=PrincipalContext.anonymous(source="test"),
    )
    assert out.agent_id == "hsk30-tutor"
    assert out.payload["reply"]
    assert out.payload["backend"] == "stub"


def test_hsk30_package_does_not_import_stock_recap():
    pkg = importlib.import_module("agent_platform.agents.hsk30_tutor.use_case")
    source_path = pkg.__file__
    assert source_path
    text = open(source_path, encoding="utf-8").read()
    assert "stock_recap" not in text


def test_cli_once_mode(settings_no_llm):
    from argparse import Namespace

    from agent_platform.agents.hsk30_tutor.cli import run

    code = run(
        Namespace(
            once=True,
            message="你好",
            level=1,
            locale="both",
            json=False,
        ),
        settings_no_llm,
        argparse.ArgumentParser(),
    )
    assert code == 0


def test_http_chat_direct(settings_no_llm):
    from agent_platform.adapters.http.app import create_app

    client = TestClient(create_app())
    r = client.post(
        "/v1/hsk30-tutor/chat/direct",
        json={"message": "谢谢", "level": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["level"] == 1
