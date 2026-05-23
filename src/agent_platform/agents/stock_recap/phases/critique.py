"""Critique — 规则化 auto_eval。"""
from __future__ import annotations

from typing import Any

from agent_platform.agents.stock_recap.llm.eval import auto_eval
from agent_platform.agents.stock_recap.phases._helpers import span_phase
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState


def run(state: RecapAgentRunState, tracer: Any) -> None:
    with span_phase(tracer, "recap.agent.critique", {"agent.phase": "critique"}):
        assert state.snapshot is not None and state.features is not None
        state.eval_result = auto_eval(state.recap, state.snapshot, state.features)


class CritiquePhase(RecapPhase):
    name = "critique"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["CritiquePhase", "run"]
