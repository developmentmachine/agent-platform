"""Recall — 历史 / 进化指引 / 向量记忆 / 实验分桶。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class RecallPhase(RecapPhase):
    name = "recall"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.agents.stock_recap import legacy_pipeline as legacy
        legacy._phase_recall(state, self._tracer())


__all__ = ["RecallPhase"]
