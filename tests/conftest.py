"""共享测试 fixtures。"""
from __future__ import annotations

import pytest

from agent_platform.config.settings import Settings


@pytest.fixture
def settings_no_llm(monkeypatch):
    """Settings 实例，不加载 .env，无 OPENAI_API_KEY（走 stub 模式）。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return Settings(_env_file=None, openai_api_key=None, recap_api_key=None)


@pytest.fixture
def settings_with_llm(monkeypatch):
    """Settings 实例，带模拟 LLM 配置。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return Settings(
        _env_file=None, recap_api_key=None,
        OPENAI_API_KEY="test-key", OPENAI_BASE_URL="http://test", RECAP_MODEL="test-model",
    )
