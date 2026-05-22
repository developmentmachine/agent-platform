"""调度 adapter — APScheduler 定时触发。

W1：透明 re-export 现有 ``interfaces.scheduler.jobs``；后续 commit 改写为
「按 AgentDefinition.capabilities=SCHEDULED 自动绑定 cron」。
"""
from agent_platform.interfaces.scheduler.jobs import start_scheduler

__all__ = ["start_scheduler"]
