"""Act — 调 LLM（含 Critic Retry）。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class ActPhase(RecapPhase):
    name = "act"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.agents.stock_recap import legacy_pipeline as legacy
        legacy._phase_act(state, self._tracer())


__all__ = ["ActPhase"]
