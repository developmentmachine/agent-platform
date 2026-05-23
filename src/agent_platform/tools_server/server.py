"""tools_server 独立 MCP server 入口（W2 起从 ``tools_server.registry`` 自动注册）。

Cursor / Claude Desktop / 任何 MCP 宿主指向本入口（``agent-platform-tools-mcp``
或 ``stock-recap-mcp``），即可获得平台所有工具。

注意：stdio 下 **stdout 仅允许 JSON-RPC**；日志只能走 stderr。
"""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.logging import configure_logging as configure_mcp_logging

from agent_platform.tools_server.registry import build_default_registry

logger = logging.getLogger("agent_platform.tools_server.server")


def _build_mcp() -> FastMCP:
    mcp = FastMCP("agent-platform-tools")
    registry = build_default_registry()
    for spec in registry.list():
        # FastMCP 的 .tool() 装饰器从函数签名推导参数；这里直接用 spec.handler，
        # 它已是 ``(**kwargs) -> str`` 形态，FastMCP 会按 input_schema 校验入参。
        mcp.add_tool(
            spec.handler,
            name=spec.name,
            description=spec.description,
        )
    return mcp


mcp = _build_mcp()


def run_server() -> None:
    """阻塞运行 MCP stdio 服务。"""
    configure_mcp_logging("WARNING")
    print(
        "agent-platform tools MCP (stdio): JSON-RPC on stdout only — do not press "
        "Enter here; spawn this command from your MCP host.",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()


__all__ = ["mcp", "run_server", "main"]
