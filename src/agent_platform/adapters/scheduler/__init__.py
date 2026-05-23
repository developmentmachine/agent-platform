"""调度 adapter — APScheduler 定时触发（按 AgentRegistry 自动绑定 cron）。"""
from agent_platform.adapters.scheduler.jobs import start_scheduler

__all__ = ["start_scheduler"]
