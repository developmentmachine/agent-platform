"""MCP stdio adapter — 以 MCP server 形式对外暴露 Agent 能力。

W1：透明 re-export 现有 ``interfaces.mcp_stdio.main``；与新建 ``tools_server`` 共享
同一进程入口（``tools_server`` 是「工具」服务，本 adapter 是「Agent」服务，
两者协议同为 MCP，路径未来可独立演化）。
"""
from agent_platform.interfaces.mcp_stdio import main

__all__ = ["main"]
