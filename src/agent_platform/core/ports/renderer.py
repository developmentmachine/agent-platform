"""渲染 Port：把结构化 Agent 输出转成具体表现形式（Markdown / WeChat 文本 / HTML…）。

每个 Agent 自己提供 renderer 实现并在 ``AgentDefinition.renderers`` 中声明可用形态。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RendererPort(Protocol):
    """把任意 Agent 的响应模型渲染成可读字符串。"""

    name: str

    def render(self, payload: Any) -> str:
        ...
