"""MCP stdio adapter — 以 MCP server 形式对外暴露 Agent 能力。

Re-export ``tools_server.server.main`` 作为 MCP stdio 入口（``tools_server`` 是「工具」服务，
本 adapter 是「Agent」服务，两者协议同为 MCP，路径未来可独立演化）。
"""
from agent_platform.tools_server.server import main

__all__ = ["main"]
