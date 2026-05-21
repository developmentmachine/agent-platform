"""tools_server — 平台内置 MCP server（独立进程入口）。

设计原则：
- 工具集中在此包，**Agent 不写自己的 tool handler**；新工具集中加在
  ``handlers/`` 下，所有 Agent 通过 MCP 客户端访问；
- 与 Cursor Desktop / Claude Desktop / Cursor CLI / Gemini CLI 同协议，
  零摩擦挂载；
- 治理（白名单 / 角色 / per-tool budget / 审计）由 runtime 的 McpToolGateway
  在客户端侧统一包装，server 端只暴露能力本身。

W1 迁移策略：
- ``server`` re-export 现有 ``interfaces.mcp_stdio.main``；
- ``handlers`` 直接 re-export ``infrastructure.tools.handlers.*``；
- 后续 commit 物理迁入此包，旧路径转为 shim。
"""
from agent_platform.interfaces.mcp_stdio import main as run_server, mcp  # noqa: F401

__all__ = ["run_server", "mcp"]
