"""平台服务入口：调度器、HTTP 应用、CLI REPL。

实现层在 adapters/，此处用惰性导入避免 agents → adapters 依赖。
"""
from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "start_scheduler":
        from agent_platform.adapters.scheduler.jobs import start_scheduler
        return start_scheduler
    if name == "create_app":
        from agent_platform.adapters.http.app import create_app
        return create_app
    if name == "run_repl":
        from agent_platform.adapters.cli.repl import run_repl
        return run_repl
    raise AttributeError(name)


__all__ = ["create_app", "run_repl", "start_scheduler"]
