"""Recap 管线编排：阶段顺序、预算、指标与 NDJSON 流。

各阶段业务实现位于 ``agents.stock_recap.phases.*``；本模块只保留
``execute_recap_pipeline`` / ``iter_recap_agent_ndjson`` 及共享编排逻辑。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Iterator, Optional, Tuple

from opentelemetry import trace

from agent_platform.agents.stock_recap.phases import (
    act,
    critique,
    index_memory,
    perceive,
    persist,
    plan,
    recall,
    reflect,
)
from agent_platform.agents.stock_recap.phases._helpers import stable_json, utc_now_iso
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.domain.models import GenerateResponse, LlmBudgetExceeded
from agent_platform.infra.llm.backends import model_effective
from agent_platform.runtime.observability.metrics import record_phase_duration, record_recap_run
from agent_platform.runtime.observability.tracing import get_tracer

logger = logging.getLogger("agent_platform.agents.stock_recap.legacy_pipeline")

PhaseName = str

# 供 legacy / pipeline_v2 共用的阶段顺序（实现已迁入 phases 包）。
_phase_perceive = perceive.run
_phase_recall = recall.run
_phase_plan = plan.run
_phase_act = act.run
_phase_critique = critique.run
_phase_persist = persist.run
_phase_index_memory = index_memory.run
_phase_reflect = reflect.run

_PHASE_ORDER: Tuple[Tuple[PhaseName, Callable[[RecapAgentRunState, Any], None]], ...] = (
    ("perceive", _phase_perceive),
    ("recall", _phase_recall),
    ("plan", _phase_plan),
    ("act", _phase_act),
    ("critique", _phase_critique),
    ("persist", _phase_persist),
    ("index_memory", _phase_index_memory),
    ("reflect", _phase_reflect),
)


def _build_generate_response(state: RecapAgentRunState) -> GenerateResponse:
    req = state.request
    settings = state.settings
    run_ctx = state.run_ctx
    request_id = run_ctx.request_id
    assert state.snapshot is not None and state.features is not None
    return GenerateResponse(
        request_id=request_id,
        created_at=utc_now_iso(),
        prompt_version=state.prompt_version,
        model=model_effective(settings, req.model) if req.force_llm else None,
        provider=req.provider,
        snapshot=state.snapshot,
        features=state.features,
        recap=state.recap,
        rendered_markdown=state.rendered_markdown,
        rendered_wechat_text=state.rendered_wechat_text,
        eval=state.eval_result,
        memory_used=[
            {"date": m.get("date"), "prompt_version": m.get("prompt_version")}
            for m in state.memory
        ],
        memory_recall={
            **(state.memory_recall_meta or {}),
            "short_term_run_count": len(state.memory or []),
            "long_term_block_count": len(state.memory_long or []),
            "entity_block_count": len(state.memory_entities or []),
        },
        push_result=state.push_result,
        error=state.llm_error,
    )


def _finalize_span_attributes(state: RecapAgentRunState) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("recap.prompt_version", state.prompt_version)
        if state.llm_error:
            span.set_attribute("recap.llm_error", True)


def _check_budget_between_phases(state: RecapAgentRunState, name: str) -> bool:
    """阶段间显式校验墙钟预算；超限则让后续阶段「轻量降级」。"""
    if state.budget is None:
        return True
    try:
        state.budget.check()
    except LlmBudgetExceeded as e:
        if state.llm_error is None:
            state.llm_error = f"budget_exceeded({e.kind}: used={e.used} limit={e.limit})"
        if state.budget_error is None:
            state.budget_error = f"{e.kind}:{e.used}/{e.limit}"
        logger.warning(
            stable_json(
                {
                    "event": "phase_budget_exceeded",
                    "phase_about_to_run": name,
                    "kind": e.kind,
                    "used": e.used,
                    "limit": e.limit,
                }
            )
        )
        return False
    return True


def _run_phase_with_metrics(
    state: RecapAgentRunState, tracer: Any, name: str, fn: Callable[[RecapAgentRunState, Any], None]
) -> None:
    t0 = time.monotonic()
    try:
        fn(state, tracer)
    except Exception:
        record_phase_duration(f"{name}:error", (time.monotonic() - t0) * 1000.0)
        raise
    record_phase_duration(name, (time.monotonic() - t0) * 1000.0)


def _record_run_outcome(state: RecapAgentRunState) -> None:
    req = state.request
    if state.llm_error and state.recap is None:
        status = "failed"
    elif state.recap is not None:
        status = "ok"
    else:
        status = "empty"
    record_recap_run(mode=str(req.mode), provider=str(req.provider), status=status)


def _run_all_phases(state: RecapAgentRunState, tracer: Any) -> GenerateResponse:
    for name, fn in _PHASE_ORDER:
        ok = _check_budget_between_phases(state, name)
        if not ok and name in {"act", "critique", "index_memory"}:
            continue
        _run_phase_with_metrics(state, tracer, name, fn)
    _finalize_span_attributes(state)
    _record_run_outcome(state)
    return _build_generate_response(state)


def execute_recap_pipeline(state: RecapAgentRunState) -> GenerateResponse:
    """在已建立的 ``recap.generate`` 父 span 与 RunContext 下执行各 Agent 阶段。"""
    tracer = get_tracer(__name__)
    return _run_all_phases(state, tracer)


def _ndjson_line(event: str, **fields: Any) -> str:
    row: dict[str, Any] = {"event": event, **fields}
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def iter_recap_agent_ndjson(state: RecapAgentRunState) -> Iterator[str]:
    """按阶段产出 NDJSON 行；最后一行为 ``result``。"""
    tracer = get_tracer(__name__)
    req = state.request
    run_ctx = state.run_ctx
    yield _ndjson_line(
        "meta",
        request_id=run_ctx.request_id,
        trace_id=run_ctx.trace_id,
        session_id=run_ctx.session_id,
        mode=req.mode,
        provider=str(req.provider),
        defer_evolution_backtest=state.defer_evolution_backtest,
    )

    last_phase: Optional[str] = None
    try:
        for name, fn in _PHASE_ORDER:
            last_phase = name
            ok = _check_budget_between_phases(state, name)
            if not ok and name in {"act", "critique", "index_memory"}:
                yield _ndjson_line(
                    "phase",
                    phase=name,
                    skipped=True,
                    reason="budget_exceeded",
                    budget_error=state.budget_error,
                )
                continue
            _run_phase_with_metrics(state, tracer, name, fn)
            extra: dict[str, Any] = {}
            if state.snapshot is not None:
                extra["date"] = state.snapshot.date
            if name == "act":
                extra["has_recap"] = state.recap is not None
                extra["llm_error"] = state.llm_error
                if state.budget_error:
                    extra["budget_error"] = state.budget_error
            yield _ndjson_line("phase", phase=name, **extra)
    except Exception as e:
        logger.exception(
            stable_json(
                {
                    "event": "recap_stream_phase_failed",
                    "phase": last_phase,
                    "error": str(e),
                }
            )
        )
        yield _ndjson_line(
            "error",
            phase=last_phase,
            message=str(e),
            request_id=run_ctx.request_id,
            trace_id=run_ctx.trace_id,
        )
        return

    _finalize_span_attributes(state)
    _record_run_outcome(state)
    resp = _build_generate_response(state)
    http_status = 503 if (req.force_llm and resp.recap is None) else 200
    state.stream_pipeline_completed = True
    yield _ndjson_line("result", http_status=http_status, body=resp.model_dump())
