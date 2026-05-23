"""Act — 调 LLM（含 Critic Retry）。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent_platform.agents.stock_recap.phases._helpers import span_phase, stable_json
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.render import render_markdown, render_wechat_text
from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.core.domain.models import LlmBudgetExceeded, LlmBusinessError
from agent_platform.infra.llm.backends import call_llm
from agent_platform.infra.guardrail.guardrails import coerce_recap_output

logger = logging.getLogger("agent_platform.agents.stock_recap.phases.act")

_CRITIC_FEEDBACK_TEMPLATE = (
    "你的上一次输出被自动校验拦截，原因如下：\n"
    "{reason}\n\n"
    "请严格按既定 JSON schema 重新输出。"
    "不要复述本条反馈，只输出符合 schema 的最终 JSON。"
)


def _inject_critic_feedback(state: RecapAgentRunState, reason: str) -> None:
    state.messages.append(
        {
            "role": "user",
            "content": _CRITIC_FEEDBACK_TEMPLATE.format(reason=reason),
        }
    )


def run(state: RecapAgentRunState, tracer: Any) -> None:
    req = state.request
    settings = state.settings
    with span_phase(tracer, "recap.agent.act", {"agent.phase": "act", "llm.forced": req.force_llm}):
        assert state.snapshot is not None and state.features is not None
        if not req.force_llm:
            return

        max_attempts = 1 + max(0, int(settings.agent_critic_max_retries))
        last_business_err: Optional[LlmBusinessError] = None

        for attempt in range(max_attempts):
            try:
                state.recap, state.tokens = call_llm(
                    settings=settings,
                    mode=req.mode,
                    messages=state.messages,
                    model_spec=req.model,
                    db_path=settings.db_path,
                    date=state.snapshot.date,
                )
                state.recap = coerce_recap_output(state.recap)
                state.rendered_markdown = render_markdown(state.recap)
                state.rendered_wechat_text = render_wechat_text(state.recap)
                state.llm_error = None
                if attempt > 0:
                    logger.info(
                        stable_json(
                            {
                                "event": "critic_retry_succeeded",
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                            }
                        )
                    )
                return
            except LlmBudgetExceeded as e:
                state.budget_error = f"{e.kind}:{e.used}/{e.limit}"
                state.llm_error = f"budget_exceeded({e.kind}: used={e.used} limit={e.limit})"
                logger.warning(
                    stable_json(
                        {
                            "event": "act_budget_exceeded",
                            "kind": e.kind,
                            "used": e.used,
                            "limit": e.limit,
                            "attempt": attempt + 1,
                        }
                    )
                )
                return
            except LlmBusinessError as e:
                last_business_err = e
                state.llm_error = f"business_error: {e}"
                if attempt + 1 < max_attempts:
                    state.critic_retries_used = attempt + 1
                    _inject_critic_feedback(state, str(e))
                    logger.warning(
                        stable_json(
                            {
                                "event": "critic_retry",
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "reason": str(e),
                            }
                        )
                    )
                    continue
                logger.error(
                    stable_json(
                        {
                            "event": "critic_retry_exhausted",
                            "attempts": max_attempts,
                            "reason": str(last_business_err),
                        }
                    )
                )
                return
            except Exception as e:
                state.llm_error = str(e)
                logger.error(stable_json({"event": "generate_failed", "error": state.llm_error}))
                return


class ActPhase(RecapPhase):
    name = "act"

    def run(self, state: RecapRunState) -> None:
        run(state, self._tracer())


__all__ = ["ActPhase", "run"]
