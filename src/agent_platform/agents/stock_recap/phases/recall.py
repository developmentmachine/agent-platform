"""Recall — 短期/向量记忆、进化指引、实验分桶。"""
from __future__ import annotations

from typing import Any

from agent_platform.agents.stock_recap.experiments import select_variant
from agent_platform.agents.stock_recap.memory.manager import (
    extract_market_patterns,
    get_prompt_version,
    load_evolution_guidance,
    load_recent_memory,
)
from agent_platform.agents.stock_recap.memory.vector_ops import recall_vector_memory
from agent_platform.agents.stock_recap.phases._helpers import span_phase, stable_json
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.agents.stock_recap.effects.backtest import load_recent_backtests_simple
from agent_platform.infra.persistence.db import load_feedback_summary

import logging

logger = logging.getLogger("agent_platform.agents.stock_recap.phases.recall")


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    settings = state.settings
    with span_phase(tracer, "recap.agent.recall", {"agent.phase": "recall"}):
        assert state.snapshot is not None and state.features is not None
        tenant_id = state.run_ctx.tenant_id
        state.memory = load_recent_memory(
            settings.db_path,
            date=state.snapshot.date,
            mode=req.mode,
            limit=settings.max_history_for_context,
            tenant_id=tenant_id,
        )
        state.evolution_guidance = load_evolution_guidance(settings.db_path)
        state.feedback_summary = load_feedback_summary(settings.db_path, tenant_id=tenant_id)

        try:
            state.pattern_summary = extract_market_patterns(
                settings.db_path,
                days=settings.pattern_extraction_days,
                settings=settings,
                model_spec=req.model,
            )
        except Exception as e:
            logger.warning(
                stable_json({"event": "pattern_extraction_skipped", "error": str(e)})
            )
            state.pattern_summary = None

        bt_history = load_recent_backtests_simple(settings.db_path, limit=3)
        if bt_history:
            state.backtest_context = "近期回测评分：" + " | ".join(
                f"{b['strategy_date']} 命中率={b.get('hit_rate', 0):.0%}" for b in bt_history
            )
        else:
            state.backtest_context = None

        state.prompt_version = get_prompt_version(settings.db_path)

        long_m, ent_m, vec_meta = recall_vector_memory(
            settings,
            tenant_id=tenant_id,
            mode=req.mode,
            snapshot=state.snapshot,
            features=state.features,
        )
        state.memory_long = long_m
        state.memory_entities = ent_m
        state.memory_recall_meta = vec_meta

        stickiness = state.run_ctx.session_id or state.run_ctx.request_id
        assignment = select_variant(
            settings.db_path, mode=req.mode, stickiness_key=stickiness
        )
        if assignment is not None:
            state.experiment_id = assignment.experiment_id
            state.variant_id = assignment.variant_id
            state.prompt_version = assignment.prompt_version
            logger.info(
                stable_json(
                    {
                        "event": "prompt_variant_assigned",
                        "experiment_id": assignment.experiment_id,
                        "variant_id": assignment.variant_id,
                        "prompt_version": assignment.prompt_version,
                    }
                )
            )


class RecallPhase(RecapPhase):
    name = "recall"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["RecallPhase", "run"]
