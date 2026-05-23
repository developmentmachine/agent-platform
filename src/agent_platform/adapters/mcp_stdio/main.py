"""Model Context Protocol（stdio）工具服务 — W2 起为 ``tools_server.server`` 的 shim。

保留旧的脚本入口（``stock-recap-mcp``）与导入路径，避免外部 MCP host 配置失效；
真实实现在 :mod:`agent_platform.tools_server.server`。
"""
from __future__ import annotations

from agent_platform.tools_server.server import main, mcp, run_server as run_mcp_stdio

__all__ = ["mcp", "run_mcp_stdio", "main"]


if __name__ == "__main__":
    main()
