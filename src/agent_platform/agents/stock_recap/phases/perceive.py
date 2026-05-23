"""Perceive — 行情采集 + 特征构建。"""
from __future__ import annotations

from typing import Any

from agent_platform.agents.stock_recap.data.collector import collect_snapshot
from agent_platform.agents.stock_recap.data.features import build_features
from agent_platform.agents.stock_recap.phases._helpers import span_phase
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    with span_phase(tracer, "recap.agent.perceive", {"agent.phase": "perceive"}):
        state.snapshot = collect_snapshot(
            req.provider,
            req.date,
            skip_trading_check=req.skip_trading_check,
        )
        state.features = build_features(state.snapshot)


class PerceivePhase(RecapPhase):
    name = "perceive"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["PerceivePhase", "run"]
