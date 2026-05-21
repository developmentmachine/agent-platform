"""LLM 后端 Port：上层调用方只依赖该协议，具体后端在 ``infra/llm/providers``。

兼容现有 ``infrastructure.llm.providers.base.LlmProvider``：本协议是其更通用的
重新表述，旧实现可通过 typing 兼容直接满足本 Protocol。
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class LlmBackendPort(Protocol):
    """与 LLM 通讯的最小抽象（覆盖普通生成 + tool-calling）。"""

    name: str

    def call(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        timeout_s: int,
        tools: List[Dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        """同步调用：返回 ``(content, meta)``；meta 至少含 ``input_tokens / output_tokens``。"""
        ...
