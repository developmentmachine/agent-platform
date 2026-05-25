"""``AgentBudget`` 的新规范位置 — re-export 老实现。"""
from agent_platform.application.orchestration.budget import AgentBudget  # noqa: F401

__all__ = ["AgentBudget"]
