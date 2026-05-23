"""Persist — 落库 runs + 可选 audit。"""
from __future__ import annotations

import logging
import time
from typing import Any

from agent_platform.agents.stock_recap.phases._helpers import span_phase, stable_json, utc_now_iso
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.infra.llm.backends import model_effective
from agent_platform.infra.persistence.db import insert_recap_audit, insert_run

logger = logging.getLogger("agent_platform.agents.stock_recap.phases.persist")


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    settings = state.settings
    run_ctx = state.run_ctx
    latency_ms = int((time.time() - state.t0) * 1000)
    with span_phase(
        tracer,
        "recap.agent.persist",
        {"agent.phase": "persist", "recap.latency_ms": latency_ms},
    ):
        assert state.snapshot is not None and state.features is not None
        insert_run(
            settings.db_path,
            request_id=run_ctx.request_id,
            created_at=utc_now_iso(),
            mode=req.mode,
            provider=req.provider,
            date=state.snapshot.date,
            prompt_version=state.prompt_version,
            model=model_effective(settings, req.model) if req.force_llm else None,
            snapshot=state.snapshot,
            features=state.features,
            recap=state.recap,
            rendered_markdown=state.rendered_markdown,
            rendered_wechat_text=state.rendered_wechat_text,
            eval_obj=state.eval_result,
            error=state.llm_error,
            latency_ms=latency_ms,
            tokens=state.tokens,
            experiment_id=state.experiment_id,
            variant_id=state.variant_id,
            tenant_id=run_ctx.tenant_id,
        )

        if settings.recap_audit_enabled:
            try:
                insert_recap_audit(
                    settings.db_path,
                    request_id=run_ctx.request_id,
                    created_at=utc_now_iso(),
                    mode=str(req.mode),
                    provider=str(req.provider),
                    prompt_version=state.prompt_version,
                    model=model_effective(settings, req.model) if req.force_llm else None,
                    trace_id=run_ctx.trace_id,
                    session_id=run_ctx.session_id,
                    messages=state.messages or None,
                    recap=state.recap,
                    eval_obj=state.eval_result or None,
                    tokens=state.tokens,
                    llm_error=state.llm_error,
                    budget_error=state.budget_error,
                    critic_retries_used=state.critic_retries_used,
                    experiment_id=state.experiment_id,
                    variant_id=state.variant_id,
                    tenant_id=run_ctx.tenant_id,
                )
            except Exception as e:
                logger.warning(
                    stable_json({"event": "recap_audit_write_failed", "error": str(e)})
                )


class PersistPhase(RecapPhase):
    name = "persist"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["PersistPhase", "run"]
