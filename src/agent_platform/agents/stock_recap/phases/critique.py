"""Critique — auto_eval 评测产物。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class CritiquePhase(RecapPhase):
    name = "critique"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.agents.stock_recap import legacy_pipeline as legacy
        legacy._phase_critique(state, self._tracer())


__all__ = ["CritiquePhase"]
