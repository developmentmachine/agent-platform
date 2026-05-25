"""Agent 工具层：schema 与执行入口（W2 起为 ``tools_server`` + ``runtime.McpToolGateway`` shim）。"""
from agent_platform.infrastructure.tools.registry import (
    execute_tool,
    prefetch_for_prompt,
)
from agent_platform.infrastructure.tools.runner import RecapToolRunner


def __getattr__(name: str):
    if name in {"TOOL_SCHEMAS", "ALL_TOOL_NAMES"}:
        from agent_platform.infrastructure.tools import registry as _reg

        return getattr(_reg, name)
    raise AttributeError(name)


__all__ = [
    "TOOL_SCHEMAS",
    "ALL_TOOL_NAMES",
    "RecapToolRunner",
    "execute_tool",
    "prefetch_for_prompt",
]
