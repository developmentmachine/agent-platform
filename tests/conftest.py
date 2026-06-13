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


@pytest.fixture
def fresh_settings(tmp_path, monkeypatch):
    """Reset the Settings singleton and return a fresh instance via env vars.

    Eliminates the repeated boilerplate::

        import agent_platform.config.settings as _settings_mod
        _settings_mod._settings_instance = None
        settings = _settings_mod.Settings()
    """
    import agent_platform.config.settings as _settings_mod

    db = tmp_path / "test.db"
    monkeypatch.setenv("RECAP_DB_PATH", str(db))
    monkeypatch.setenv("RECAP_WXWORK_WEBHOOK_URL", "http://example.invalid/hook")
    monkeypatch.setenv("RECAP_PUSH_ENABLED", "false")
    monkeypatch.setenv("RECAP_API_KEY", "test-key")
    monkeypatch.setenv("RECAP_AUDIT_ENABLED", "true")

    _settings_mod._settings_instance = None  # noqa: SLF001
    return _settings_mod.Settings()


@pytest.fixture
def _wire_stock_recap_deps(fresh_settings):
    """Wire and tear-down stock_recap default deps for tests that run generate_once.

    Yields ``(settings, repo_factory)`` so tests can use them directly.
    """
    from agent_platform.agents.stock_recap.deps import configure_default_deps, reset_default_deps
    from agent_platform.infra.persistence.factory import SqliteRepositoryFactory

    rf = SqliteRepositoryFactory(fresh_settings.db_path)
    configure_default_deps(repo_factory=rf, guardrail=_NoopGuardrailForTests())
    yield fresh_settings, rf
    reset_default_deps()


class _NoopGuardrailForTests:
    """Minimal GuardrailPort stub for tests."""
    def validate_generate_request(self, req): pass
    def validate_feedback_request(self, req): pass
    def pre_input(self, text, **kw): return text
    def post_output(self, text, **kw): return text
    def clamp_messages(self, msgs, **kw): return msgs
    def coerce_recap_output(self, recap, *a, **kw): return recap
