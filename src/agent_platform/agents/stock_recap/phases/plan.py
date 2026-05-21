"""Plan — 组装 LLM messages（含 guardrails clamp）。"""
from __future__ import annotations

from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.state import RecapRunState


class PlanPhase(RecapPhase):
    name = "plan"

    def run(self, state: RecapRunState) -> None:
        from agent_platform.application.orchestration import pipeline as legacy
        legacy._phase_plan(state, self._tracer())


__all__ = ["PlanPhase"]
