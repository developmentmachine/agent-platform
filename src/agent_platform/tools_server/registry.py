"""tools_server 中央工具登记表 — 全平台唯一真实源。

设计要点：
- 一个工具 = 一条 ``ToolSpec``（name + description + JSON Schema + handler）；
- **唯一登记位置**：``tools_server.tools.<name>`` 模块导出 ``SPEC``，本文件聚合；
- MCP server（``server.py``）按 SPEC 注册到 FastMCP；
- InProcessMcpClient 同样按 SPEC 提供 ``list_tools`` / ``call``；
- LLM provider（OpenAI / Ollama function calling）需要的 schema 由 ``McpToolGateway``
  从这里推导，**不再有第二份 OpenAI schema 在别处维护**。

新增工具：在 ``tools/`` 下新建模块，导出 ``SPEC``，并在 ``REGISTRY`` 引用 — 完。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的全部元数据 + handler。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., str]
    read_only: bool = True

    def to_openai_function(self) -> Dict[str, Any]:
        """转 OpenAI / Ollama tool-calling 兼容 schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    """进程内工具登记表（只读视图）。"""

    def __init__(self, specs: List[ToolSpec]) -> None:
        self._by_name: Dict[str, ToolSpec] = {s.name: s for s in specs}

    def names(self) -> List[str]:
        return sorted(self._by_name.keys())

    def get(self, name: str) -> ToolSpec:
        return self._by_name[name]

    def has(self, name: str) -> bool:
        return name in self._by_name

    def list(self) -> List[ToolSpec]:
        return [self._by_name[n] for n in self.names()]

    def items(self) -> List[Tuple[str, ToolSpec]]:
        return [(n, self._by_name[n]) for n in self.names()]


def build_default_registry() -> ToolRegistry:
    """聚合 ``tools/`` 下的所有 SPEC。"""
    from agent_platform.tools_server.tools.history import SPEC as HISTORY_SPEC
    from agent_platform.tools_server.tools.market_data import SPEC as MARKET_DATA_SPEC
    from agent_platform.tools_server.tools.web_search import SPEC as WEB_SEARCH_SPEC

    return ToolRegistry(
        [
            WEB_SEARCH_SPEC,
            MARKET_DATA_SPEC,
            HISTORY_SPEC,
        ]
    )


__all__ = ["ToolSpec", "ToolRegistry", "build_default_registry"]
