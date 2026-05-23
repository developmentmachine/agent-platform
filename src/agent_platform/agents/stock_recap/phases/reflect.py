"""Reflect — 进化检查、推送、回测触发。"""
from __future__ import annotations

import logging
from typing import Any

from agent_platform.agents.stock_recap.effects.push import push_recap
from agent_platform.agents.stock_recap.memory.manager import check_and_run_evolution
from agent_platform.agents.stock_recap.phases._helpers import span_phase, stable_json
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.application.side_effects import try_run_backtest

logger = logging.getLogger("agent_platform.agents.stock_recap.phases.reflect")


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    settings = state.settings
    run_ctx = state.run_ctx
    request_id = run_ctx.request_id
    with span_phase(
        tracer,
        "recap.agent.reflect",
        {
            "agent.phase": "reflect",
            "recap.defer_evolution_backtest": state.defer_evolution_backtest,
        },
    ):
        if not state.defer_evolution_backtest:
            try:
                check_and_run_evolution(
                    settings.db_path,
                    settings=settings,
                    trigger_run_id=request_id,
                    force=False,
                    model_spec=req.model,
                )
            except Exception as e:
                logger.warning(
                    stable_json({"event": "evolution_check_failed", "error": str(e)})
                )

        if state.recap is not None:
            try:
                state.push_result = push_recap(
                    settings, state.recap, request_id=request_id
                )
            except Exception as e:
                logger.warning(stable_json({"event": "push_failed", "error": str(e)}))
                state.push_result = False

        if (
            not state.defer_evolution_backtest
            and req.mode == "daily"
            and state.recap is not None
        ):
            assert state.snapshot is not None
            try_run_backtest(settings.db_path, state.snapshot.date)


class ReflectPhase(RecapPhase):
    name = "reflect"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["ReflectPhase", "run"]
