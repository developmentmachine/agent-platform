"""adapters — Driving Adapters：所有对外入口。

入口类型：
- ``cli``        命令行（按 AgentRegistry 自动发现子命令）
- ``http``       FastAPI / 内部 REST（按 AgentRegistry include_router）
- ``wecom``      企业微信 AiBot connector（WebSocket / 回调）
- ``qq``         QQ 机器人 connector（WebSocket / 回调）
- ``scheduler``  APScheduler 定时触发
- ``mcp_stdio``  以 MCP server 形式对外暴露 Agent 能力（独立进程）

铁律：
- adapters 只允许 ``from agent_platform.runtime import create_runtime, AgentRuntime``；
- 禁止 import ``agent_platform.infra.*`` / ``agent_platform.agents.*``；
- 入口统一：``runtime.run(...)`` / ``runtime.stream(...)``。

W1 迁移策略：``cli`` / ``http`` / ``scheduler`` / ``mcp_stdio`` 暂以适配层方式
重用 ``interfaces.*`` 的现成入口；后续 commit 物理迁入此包。新增的
``wecom`` / ``qq`` 直接在此包落地。
"""
from agent_platform.adapters.common import (
    AdapterContext,
    NormalizedMessage,
    build_conversation_key,
)

__all__ = [
    "AdapterContext",
    "NormalizedMessage",
    "build_conversation_key",
]
