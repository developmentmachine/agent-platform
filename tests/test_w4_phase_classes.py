"""W4: 验证 recap Phase 类化与 pipeline_v2 与历史 pipeline 行为对等。"""
from __future__ import annotations

import json
import time
from typing import List, Tuple

import pytest

from agent_platform.agents.stock_recap.phases import (
    ActPhase,
    CritiquePhase,
    IndexMemoryPhase,
    PerceivePhase,
    PersistPhase,
    PlanPhase,
    RecallPhase,
    ReflectPhase,
    build_default_phases,
)
from agent_platform.agents.stock_recap.pipeline_v2 import execute_v2, iter_ndjson_v2
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.legacy_pipeline import execute_recap_pipeline
from agent_platform.config.settings import Settings
from agent_platform.core.domain.models import GenerateRequest
from agent_platform.domain.run_context import RunContext


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    for k, v in {
        "RECAP_DB_PATH": str(tmp_path / "w4.db"),
        "RECAP_AGENT_MAX_TOOL_CALLS": "0",
        "RECAP_AGENT_MAX_TOKENS": "0",
        "RECAP_AGENT_MAX_WALL_MS": "0",
        "RECAP_RECAP_AUDIT_ENABLED": "false",
        "RECAP_WECOM_BOT_URL": "",
        "RECAP_WECOM_USE_SIDECAR": "false",
    }.items():
        monkeypatch.setenv(k, v)
    from agent_platform.infra.persistence.db import init_db

    s = Settings()
    init_db(s.db_path)
    return s


# ─── Phase 类形状 ───────────────────────────────────────────────────────────


def test_recap_run_state_alias_is_recap_agent_run_state() -> None:
    assert RecapRunState is RecapAgentRunState


def test_default_phases_order_matches_legacy() -> None:
    phases = build_default_phases()
    names = [p.name for p in phases]
    assert names == [
        "perceive",
        "recall",
        "plan",
        "act",
        "critique",
        "persist",
        "index_memory",
        "reflect",
    ]


def test_each_phase_satisfies_core_phase_protocol() -> None:
    from agent_platform.core.orchestration.phase import Phase

    for klass in (
        PerceivePhase, RecallPhase, PlanPhase, ActPhase,
        CritiquePhase, PersistPhase, IndexMemoryPhase, ReflectPhase,
    ):
        instance = klass()
        assert isinstance(instance, Phase), f"{klass.__name__} 不满足 Phase 协议"


def test_phase_run_delegates_to_legacy_function(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PerceivePhase.run 必须走 phases.perceive.run。"""
    from agent_platform.agents.stock_recap.phases import perceive

    called: List[Tuple[str, object]] = []

    def _spy(state, tracer):
        called.append(("perceive", state))

    monkeypatch.setattr(perceive, "run", _spy)
    s = _settings(monkeypatch, tmp_path)
    state = RecapAgentRunState(
        request=GenerateRequest(mode="daily", provider="mock", force_llm=False),
        settings=s,
        run_ctx=RunContext.new(),
        t0=time.time(),
    )
    PerceivePhase().run(state)
    assert called and called[0][0] == "perceive"


def test_phase_stream_emits_start_then_end(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from agent_platform.agents.stock_recap import legacy_pipeline as legacy
    from agent_platform.core.orchestration.stream_events import StreamEventKind

    monkeypatch.setattr(legacy, "_phase_perceive", lambda state, tracer: None)
    s = _settings(monkeypatch, tmp_path)
    state = RecapAgentRunState(
        request=GenerateRequest(mode="daily", provider="mock", force_llm=False),
        settings=s,
        run_ctx=RunContext.new(),
        t0=time.time(),
    )
    events = list(PerceivePhase().stream(state))
    assert [e.kind for e in events] == [
        StreamEventKind.PHASE_START,
        StreamEventKind.PHASE_END,
    ]
    assert events[1].data.get("duration_ms") is not None


# ─── 端到端：execute_v2 与历史 execute_recap_pipeline 等价 ────────────────────


def _make_state(monkeypatch, tmp_path) -> RecapAgentRunState:
    s = _settings(monkeypatch, tmp_path)
    return RecapAgentRunState(
        request=GenerateRequest(mode="daily", provider="mock", force_llm=False),
        settings=s,
        run_ctx=RunContext.new(),
        t0=time.time(),
    )


def test_execute_v2_runs_all_phases(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    state = _make_state(monkeypatch, tmp_path)
    resp = execute_v2(state)
    assert resp is not None
    assert resp.provider == "mock"
    # 非 LLM 路径：recap 为空，但 snapshot 已经填好
    assert state.snapshot is not None


def test_execute_v2_vs_legacy_pipeline_same_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    state_v1 = _make_state(monkeypatch, tmp_path)
    state_v2 = _make_state(monkeypatch, tmp_path)
    r1 = execute_recap_pipeline(state_v1)
    r2 = execute_v2(state_v2)
    assert r1.provider == r2.provider == "mock"
    assert (r1.snapshot is None) == (r2.snapshot is None)
    assert (r1.recap is None) == (r2.recap is None)


def test_iter_ndjson_v2_emits_meta_phases_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    state = _make_state(monkeypatch, tmp_path)
    lines = [json.loads(x) for x in iter_ndjson_v2(state)]
    events = [x["event"] for x in lines]
    assert events[0] == "meta"
    assert events[-1] == "result"
    phase_names = [x["phase"] for x in lines if x["event"] == "phase"]
    assert phase_names == [
        "perceive",
        "recall",
        "plan",
        "act",
        "critique",
        "persist",
        "index_memory",
        "reflect",
    ]


def test_use_case_routes_pipeline_v2_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from agent_platform.agents.stock_recap import use_case as uc

    s = _settings(monkeypatch, tmp_path)
    req = GenerateRequest(mode="daily", provider="mock", force_llm=False)
    calls: list[str] = []

    from unittest.mock import MagicMock

    monkeypatch.setattr(uc, "validate_generate_request", lambda _req: None)
    monkeypatch.setattr(uc, "configure_tracing", lambda _s: None)

    def _stub_v2(_state):
        calls.append("v2")
        return MagicMock(request_id="v2")

    def _stub_legacy(_state):
        calls.append("legacy")
        return MagicMock(request_id="legacy")

    monkeypatch.setattr(uc, "execute_v2", _stub_v2)
    monkeypatch.setattr(uc, "execute_recap_pipeline", _stub_legacy)

    monkeypatch.setenv("RECAP_PIPELINE_V2", "true")
    uc.generate_once(req, Settings())
    assert calls == ["v2"]

    calls.clear()
    monkeypatch.setenv("RECAP_PIPELINE_V2", "false")
    uc.generate_once(req, Settings())
    assert calls == ["legacy"]
