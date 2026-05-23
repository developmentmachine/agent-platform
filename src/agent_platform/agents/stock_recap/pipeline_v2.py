"""recap pipeline v2 —— 基于 ``core.orchestration.Pipeline`` 与 Phase 类。

为什么不直接替换现有 ``application.orchestration.pipeline.execute_recap_pipeline``：
- 现有 streaming 实现里有「阶段间预算校验跳过 act/critique/index_memory」「最后一行
  result 注入 http_status」这两条复盘专属语义，平台 Pipeline 不应承担；
- 引入 v2 后保留两条路径，让 ``application.recap`` 在 W6 / W7 平滑切换；
- 单测可以直接对 Phase 类 mock，不再耦合长函数。

行为目标：
- ``execute_v2(state)``      —— 等价于 ``execute_recap_pipeline``；
- ``iter_ndjson_v2(state)``  —— 等价于 ``iter_recap_agent_ndjson``；
- 预算跳过逻辑与 budget_error 落库与历史保持一致。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, List

from agent_platform.agents.stock_recap.phases import RecapPhase, build_default_phases
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.agents.stock_recap.legacy_pipeline import (
    _PHASE_ORDER,
    _build_generate_response,
    _check_budget_between_phases,
    _finalize_span_attributes,
    _record_run_outcome,
    _run_phase_with_metrics,
)
from agent_platform.domain.models import GenerateResponse
from agent_platform.runtime.observability.tracing import get_tracer

logger = logging.getLogger("agent_platform.agents.stock_recap.pipeline_v2")


# 与原 pipeline._PHASE_ORDER 中跳过的 phase 集合保持一致。
_SKIP_ON_BUDGET = frozenset({"act", "critique", "index_memory"})


def _phase_dict(phases: List[RecapPhase]) -> dict[str, RecapPhase]:
    return {p.name: p for p in phases}


def _ndjson_line(event: str, **fields: Any) -> str:
    row: dict[str, Any] = {"event": event, **fields}
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def execute_v2(state: RecapRunState) -> GenerateResponse:
    """v2 入口：Pipeline = build_default_phases()。"""
    tracer = get_tracer(__name__)
    phases = build_default_phases()
    phase_map = _phase_dict(phases)
    # 与历史 _PHASE_ORDER 顺序对齐（双保险）
    for name, _ in _PHASE_ORDER:
        phase = phase_map[name]
        ok = _check_budget_between_phases(state, name)
        if not ok and name in _SKIP_ON_BUDGET:
            continue
        _run_phase_with_metrics(state, tracer, name, lambda s, _t, p=phase: p.run(s))
    _finalize_span_attributes(state)
    _record_run_outcome(state)
    return _build_generate_response(state)


def iter_ndjson_v2(state: RecapRunState) -> Iterator[str]:
    """v2 streaming：NDJSON 形态与历史等价。"""
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

    phases = build_default_phases()
    phase_map = _phase_dict(phases)
    last_phase = None
    try:
        for name, _ in _PHASE_ORDER:
            phase = phase_map[name]
            last_phase = name
            ok = _check_budget_between_phases(state, name)
            if not ok and name in _SKIP_ON_BUDGET:
                yield _ndjson_line(
                    "phase",
                    phase=name,
                    skipped=True,
                    reason="budget_exceeded",
                    budget_error=state.budget_error,
                )
                continue
            _run_phase_with_metrics(state, tracer, name, lambda s, _t, p=phase: p.run(s))
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
            "recap_v2_stream_phase_failed phase=%s err=%s", last_phase, e
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


__all__ = ["execute_v2", "iter_ndjson_v2"]
