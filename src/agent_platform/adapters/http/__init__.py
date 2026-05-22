"""HTTP adapter — FastAPI 入口。

W1：透明 re-export 现有 ``interfaces.api``；后续 commit 把每个 Agent 的路由
注册改为「按 AgentRegistry.list() 自动 include_router」。
"""
from agent_platform.interfaces.api.app import app

__all__ = ["app"]
