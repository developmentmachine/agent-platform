"""Monolith bootstrap — 注册 core 接口的 monolith 实现。

在 monolith 的 __init__.py 中调用，确保 core 的可插拔接口
（http, services）在 monolith 环境下自动连接到真实实现。
"""
from __future__ import annotations


def _register_http_deps() -> None:
    """延迟注册 HTTP 鉴权/限流实现。"""
    from agent_platform.core.http import register_http_deps
    from agent_platform.adapters.http.deps import require_api_key, require_rate_limit
    register_http_deps(require_api_key, require_rate_limit)


def _register_services() -> None:
    """延迟注册平台服务实现。"""
    from agent_platform.core.services import register_services
    from agent_platform.adapters.http.app import create_app
    from agent_platform.adapters.cli.repl import run_repl
    from agent_platform.adapters.scheduler.jobs import start_scheduler
    register_services(create_app, run_repl, start_scheduler)


def bootstrap() -> None:
    """注册所有 monolith 实现到 core 接口。幂等，可多次调用。"""
    try:
        _register_http_deps()
    except Exception:
        pass  # adapters 可能还没初始化
    try:
        _register_services()
    except Exception:
        pass
