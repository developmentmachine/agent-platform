"""Index memory — 向量库索引（可选）。"""
from __future__ import annotations

import logging
from typing import Any

from agent_platform.agents.stock_recap.memory.vector_ops import index_recap_for_memory
from agent_platform.agents.stock_recap.phases._helpers import span_phase, stable_json
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState

logger = logging.getLogger("agent_platform.agents.stock_recap.phases.index_memory")


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    run_ctx = state.run_ctx
    with span_phase(tracer, "recap.agent.index_memory", {"agent.phase": "index_memory"}):
        if state.recap is None:
            return
        try:
            index_recap_for_memory(
                state.settings,
                tenant_id=run_ctx.tenant_id,
                request_id=run_ctx.request_id,
                mode=req.mode,
                recap=state.recap,
            )
        except Exception as e:
            logger.warning(
                stable_json({"event": "index_memory_phase_failed", "error": str(e)})
            )


class IndexMemoryPhase(RecapPhase):
    name = "index_memory"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["IndexMemoryPhase", "run"]
