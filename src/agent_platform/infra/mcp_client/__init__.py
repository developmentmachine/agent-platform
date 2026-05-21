"""MCP 客户端实现 — ``core.ports.mcp_tool.McpClientPort`` 的具体实现集合。

提供三层：
- ``StdioMcpClient``  本地子进程跑 MCP server（最简、零网络，开发默认）
- ``HttpMcpClient``   远端 MCP server（HTTP/SSE，多租户共享） — 占位，后续 commit 落地
- ``MultiMcpRouter``  聚合多个 server 的工具命名空间（名字冲突显式 prefix） — 占位

工具治理（白名单 / 角色 / per-tool budget / 审计 / 超时）由
``runtime.mcp_gateway.McpToolGateway`` 在客户端外围统一包装，保证所有实现共用
同一套治理语义；这与现 ``RecapToolRunner`` 中的 policy + audit 一致，只是把
「本地 function-calling 注册表」替换为 ``McpClientPort``。
"""
from agent_platform.infra.mcp_client.stdio import StdioMcpClient

__all__ = ["StdioMcpClient"]
