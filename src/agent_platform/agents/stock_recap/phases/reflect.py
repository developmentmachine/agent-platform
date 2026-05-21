"""Reflect — 进化检查 / 推送 / 回测触发。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class ReflectPhase(RecapPhase):
    name = "reflect"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.application.orchestration import pipeline as legacy
        legacy._phase_reflect(state, self._tracer())


__all__ = ["ReflectPhase"]
