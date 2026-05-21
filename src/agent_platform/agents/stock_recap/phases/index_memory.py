"""IndexMemory — recap 入向量库（可选）。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class IndexMemoryPhase(RecapPhase):
    name = "index_memory"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.application.orchestration import pipeline as legacy
        legacy._phase_index_memory(state, self._tracer())


__all__ = ["IndexMemoryPhase"]
