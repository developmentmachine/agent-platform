"""Persist — recap_runs + recap_audit 落库。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class PersistPhase(RecapPhase):
    name = "persist"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.application.orchestration import pipeline as legacy
        legacy._phase_persist(state, self._tracer())


__all__ = ["PersistPhase"]
