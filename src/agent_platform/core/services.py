"""平台服务入口：调度器、HTTP 应用、CLI REPL。

纯接口声明。monolith 启动时通过 ``register_services()`` 注入实现。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# ── 可插拔实现注册 ──────────────────────────────────────────────

_create_app_impl: Optional[Callable[..., Any]] = None
_run_repl_impl: Optional[Callable[..., Any]] = None
_start_scheduler_impl: Optional[Callable[..., Any]] = None


def register_services(
    create_app: Callable[..., Any],
    run_repl: Callable[..., Any],
    start_scheduler: Callable[..., Any],
) -> None:
    """由 monolith 启动时调用，注入平台服务实现。"""
    global _create_app_impl, _run_repl_impl, _start_scheduler_impl
    _create_app_impl = create_app
    _run_repl_impl = run_repl
    _start_scheduler_impl = start_scheduler


def create_app(*args: Any, **kwargs: Any) -> Any:
    if _create_app_impl is None:
        raise RuntimeError("create_app not registered. Install agent-platform for full functionality.")
    return _create_app_impl(*args, **kwargs)


def run_repl(*args: Any, **kwargs: Any) -> Any:
    if _run_repl_impl is None:
        raise RuntimeError("run_repl not registered. Install agent-platform for full functionality.")
    return _run_repl_impl(*args, **kwargs)


def start_scheduler(*args: Any, **kwargs: Any) -> Any:
    if _start_scheduler_impl is None:
        raise RuntimeError("start_scheduler not registered. Install agent-platform for full functionality.")
    return _start_scheduler_impl(*args, **kwargs)


__all__ = ["create_app", "run_repl", "start_scheduler", "register_services"]
