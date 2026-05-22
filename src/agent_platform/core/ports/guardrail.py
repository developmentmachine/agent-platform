"""输入 / 输出护栏 Port — 统一拦截点（PII / 越狱 / 模型乱输出 / 合规词表）。

兼容现有 ``policy/guardrails.py`` 与 ``policy/output_rules.py``：将其作为默认
实现包装在 ``infra/guardrail`` 下。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class GuardrailDecision:
    """拦截结果。``blocked=True`` 时 ``reason`` 必有；``text`` 为护栏处理后的文本。"""

    text: str
    blocked: bool = False
    reason: Optional[str] = None


@runtime_checkable
class GuardrailPort(Protocol):
    """输入与输出两条路径的护栏抽象。"""

    def pre_input(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        ...

    def post_output(self, text: str, *, principal_role: Optional[str] = None) -> GuardrailDecision:
        ...
