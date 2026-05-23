"""Plan — 组装 LLM messages。"""
from __future__ import annotations

from typing import Any, List, cast

from agent_platform.agents.stock_recap.llm.prompts import build_messages
from agent_platform.agents.stock_recap.phases._helpers import span_phase
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.policy.guardrails import clamp_llm_messages


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    settings = state.settings
    with span_phase(tracer, "recap.agent.plan", {"agent.phase": "plan"}):
        assert state.snapshot is not None and state.features is not None
        raw_messages: List[dict[str, Any]] = list(
            build_messages(
                mode=req.mode,
                snapshot=state.snapshot,
                features=state.features,
                memory=state.memory,
                memory_long=state.memory_long,
                memory_entities=state.memory_entities,
                prompt_version=state.prompt_version,
                evolution_guidance=state.evolution_guidance,
                feedback_summary=state.feedback_summary,
                backtest_context=state.backtest_context,
                pattern_summary=state.pattern_summary,
                skill_id_override=settings.skill_id_override,
            )
        )
        state.messages = cast(List[dict[str, str]], clamp_llm_messages(raw_messages))


class PlanPhase(RecapPhase):
    name = "plan"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["PlanPhase", "run"]
