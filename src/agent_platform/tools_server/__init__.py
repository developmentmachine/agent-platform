"""tools_server — 平台内置 MCP server（独立进程入口）。

设计原则：
- 工具集中在此包，**Agent 不写自己的 tool handler**；新工具集中加在
  ``tools/`` 下，所有 Agent 通过 MCP 客户端（``McpClientPort``）访问；
- 与 Cursor Desktop / Claude Desktop / Cursor CLI / Gemini CLI 同协议，
  零摩擦挂载；
- 治理（白名单 / 角色 / per-tool budget / 审计）由 ``runtime.McpToolGateway``
  在客户端侧统一包装，server 端只暴露能力本身。

W2 状态：``server`` / ``registry`` / ``tools`` 已为唯一真实源；
``handlers/`` 子模块保留为对 ``infrastructure.tools.handlers`` 的薄 shim
（W7 一次性删除旧路径）。
"""
from agent_platform.tools_server.registry import (
    ToolRegistry,
    ToolSpec,
    build_default_registry,
)


def __getattr__(name: str):
    # Lazy import to avoid heavy FastMCP import + side effects at package load.
    if name in {"run_server", "main", "mcp"}:
        from agent_platform.tools_server.server import main, mcp, run_server

        return {"run_server": run_server, "main": main, "mcp": mcp}[name]
    raise AttributeError(name)


__all__ = [
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
    "run_server",
    "mcp",
]
