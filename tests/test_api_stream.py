"""POST /v1/recap/stream NDJSON 契约（无 LLM）。"""
import json

import pytest
from fastapi.testclient import TestClient

import agent_platform.config.settings as settings_module
from agent_platform.domain.models import GenerateRequest
from agent_platform.adapters.http.routes import app


class _NoopGuardrail:
    """Minimal guardrail stub for tests that don't exercise guardrails."""

    def validate_generate_request(self, req):  # noqa: ANN001
        pass

    def validate_feedback_request(self, req):  # noqa: ANN001
        pass

    def pre_input(self, text, **kw):  # noqa: ANN001
        return text

    def post_output(self, text, **kw):  # noqa: ANN001
        return text

    def clamp_messages(self, msgs, **kw):  # noqa: ANN001
        return msgs

    def coerce_recap_output(self, recap, *a, **kw):  # noqa: ANN001
        return recap


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    settings_module._settings_instance = None
    db = str(tmp_path / "api_stream.db")
    monkeypatch.setenv("RECAP_DB_PATH", db)
    monkeypatch.delenv("RECAP_API_KEY", raising=False)
    monkeypatch.delenv("RECAP_OTEL_ENABLED", raising=False)

    from agent_platform.infra.persistence.db import init_db
    from agent_platform.infra.persistence.factory import SqliteRepositoryFactory
    from agent_platform.agents.stock_recap.deps import configure_default_deps, reset_default_deps
    from agent_platform.infra.policy.guardrail_adapter import GuardrailAdapter

    init_db(db)
    rf = SqliteRepositoryFactory(db)
    configure_default_deps(repo_factory=rf, guardrail=GuardrailAdapter())
    yield TestClient(app)
    reset_default_deps()


def test_recap_stream_ndjson_phases_and_result(client: TestClient) -> None:
    req = {
        "mode": "daily",
        "provider": "mock",
        "force_llm": False,
    }
    lines: list[str] = []
    with client.stream("POST", "/v1/recap/stream", json=req) as r:
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/x-ndjson")
        for raw in r.iter_lines():
            if raw:
                lines.append(raw)

    assert len(lines) >= 9
    events = [json.loads(line) for line in lines]
    assert events[0]["event"] == "meta"
    assert events[0]["mode"] == "daily"
    phases = [e["phase"] for e in events[1:-1] if e.get("event") == "phase"]
    assert phases == [
        "perceive",
        "recall",
        "plan",
        "act",
        "critique",
        "persist",
        "index_memory",
        "reflect",
    ]
    last = events[-1]
    assert last["event"] == "result"
    assert last["http_status"] == 200
    assert "body" in last
    assert last["body"]["request_id"] == events[0]["request_id"]


def test_recap_stream_validates_date(client: TestClient) -> None:
    r = client.post(
        "/v1/recap/stream",
        json=GenerateRequest(date="not-a-date", provider="mock", force_llm=False).model_dump(),
    )
    assert r.status_code == 400


def test_recap_stream_error_event_on_phase_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object):
        raise RuntimeError("stream_phase_boom")

    monkeypatch.setattr(
        "agent_platform.agents.stock_recap.legacy_pipeline.collect_snapshot",
        boom,
    )
    lines: list[str] = []
    with client.stream(
        "POST",
        "/v1/recap/stream",
        json={"mode": "daily", "provider": "mock", "force_llm": False},
    ) as r:
        assert r.status_code == 200
        for raw in r.iter_lines():
            if raw:
                lines.append(raw)
    events = [json.loads(x) for x in lines]
    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "error"
    assert "stream_phase_boom" in events[-1].get("message", "")
    assert events[-1].get("phase") == "perceive"
