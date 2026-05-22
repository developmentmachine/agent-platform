"""Perceive — 行情采集 + 特征构建。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class PerceivePhase(RecapPhase):
    name = "perceive"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.agents.stock_recap import legacy_pipeline as legacy
        legacy._phase_perceive(state, self._tracer())


__all__ = ["PerceivePhase"]
