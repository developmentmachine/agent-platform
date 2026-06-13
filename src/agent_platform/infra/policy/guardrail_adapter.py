"""GuardrailPort 的具体实现：包装 ``policy.guardrails`` 中已有的函数。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_platform.core.ports.guardrail import GuardrailDecision, GuardrailError  # noqa: F401
from agent_platform.infra.policy.guardrails import (
    clamp_llm_messages,
    coerce_recap_output as _coerce_recap_output,
    validate_feedback_request as _validate_feedback_request,
    validate_generate_request as _validate_generate_request,
)


class GuardrailAdapter:
    """GuardrailPort 的具体实现，桥接 core port 与 infra 策略函数。

    ``pre_input`` / ``post_output`` 为占位实现（直接透传），待后续
    接入 PII / 越狱检测时再替换。
    """

    # ── pre / post ────────────────────────────────────────────────────────

    def pre_input(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        return GuardrailDecision(text=text)

    def post_output(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        return GuardrailDecision(text=text)

    # ── 请求校验 ─────────────────────────────────────────────────────────

    def validate_generate_request(self, req: Any) -> None:
        _validate_generate_request(req)

    def validate_feedback_request(self, req: Any) -> None:
        _validate_feedback_request(req)

    # ── 消息截断 ─────────────────────────────────────────────────────────

    def clamp_messages(self, messages: List[Dict[str, Any]], max_chars: int = 1_200_000) -> List[Dict[str, Any]]:
        return clamp_llm_messages(messages, max_total_chars=max_chars)

    # ── 输出合规 ─────────────────────────────────────────────────────────

    def coerce_recap_output(self, recap: Any, *args: Any, **kwargs: Any) -> Any:
        return _coerce_recap_output(recap, *args, **kwargs)
