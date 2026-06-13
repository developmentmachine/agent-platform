"""输入 / 输出护栏 Port — 统一拦截点（PII / 越狱 / 模型乱输出 / 合规词表）。

兼容现有 ``policy/guardrails.py`` 与 ``policy/output_rules.py``：将其作为默认
实现包装在 ``infra/guardrail`` 下。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class GuardrailError(ValueError):
    """护栏拒绝的请求。"""


@dataclass
class GuardrailDecision:
    """拦截结果。``blocked=True`` 时 ``reason`` 必有；``text`` 为护栏处理后的文本。"""

    text: str
    blocked: bool = False
    reason: Optional[str] = None


@runtime_checkable
class GuardrailPort(Protocol):
    """输入与输出两条路径的护栏抽象。

    除了 ``pre_input`` / ``post_output`` 之外，还覆盖 stock_recap
    的实际使用场景：请求校验、消息截断、输出合规。
    """

    def pre_input(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        ...

    def post_output(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        ...

    def validate_generate_request(self, req: Any) -> None:
        """校验 GenerateRequest，失败时抛出 GuardrailError。"""
        ...

    def validate_feedback_request(self, req: Any) -> None:
        """校验 FeedbackRequest，失败时抛出 GuardrailError。"""
        ...

    def clamp_messages(self, messages: List[Dict[str, Any]], max_chars: int = 1_200_000) -> List[Dict[str, Any]]:
        """截断超长 LLM 消息，防止撑爆上下文。"""
        ...

    def coerce_recap_output(self, recap: Any, *args: Any, **kwargs: Any) -> Any:
        """输出侧护栏：词表脱敏 + 必含词 + 一致性 + disclaimer 兜底。"""
        ...
