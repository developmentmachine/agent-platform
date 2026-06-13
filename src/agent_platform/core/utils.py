"""共享工具函数：供 core / agents / adapters 共用，无上层依赖。

提供：
- ``stable_json`` — 确定性 JSON 序列化
- ``resolve_from_context`` — 从 ContextVar 链解析字段（tenant_id / role 等）
- ``logged_errors`` — 结构化异常日志装饰器
- ``contextvars_block`` — ContextVar 批量 set/reset 上下文管理器
"""
from __future__ import annotations

import functools
import json
import logging
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypeVar

# ─── 基础工具 ────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str() -> str:
    """当前本地日期的 YYYY-MM-DD 字符串。"""
    return datetime.now().strftime("%Y-%m-%d")


def stable_json(obj: Any) -> str:
    """稳定的 JSON 序列化（ensure_ascii=False, sort_keys=True）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ─── ContextVar 工具 ─────────────────────────────────────────────────────────

_SENTINEL = object()

class contextvars_block:
    """批量设置 ContextVar，退出时自动恢复。

    用法::

        # 方式一：直接传 ContextVar 对象（推荐，不限于本模块变量）
        with contextvars_block({current_run_context: run_ctx, current_budget: budget}):
            ...

        # 方式二：通过变量名字符串查找本模块 globals（向后兼容）
        with contextvars_block(current_run_context=run_ctx):
            ...

    替代常见的 ``token = ctx.set(v); try: ...; finally: ctx.reset(token)`` 模式。
    """

    def __init__(
        self,
        mappings: Optional[Dict[ContextVar, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._assignments: list[tuple[ContextVar, Token]] = []
        self._mappings = mappings or {}
        self._kwargs = kwargs

    def __enter__(self) -> "contextvars_block":
        # Handle direct ContextVar → value mappings
        for cv, value in self._mappings.items():
            token = cv.set(value)
            self._assignments.append((cv, token))
        # Handle string-keyed lookups (backwards compatible)
        for var, value in self._kwargs.items():
            cv: ContextVar = globals().get(var)  # type: ignore[assignment]
            if cv is None:
                raise ValueError(f"ContextVar '{var}' not found in module globals")
            token = cv.set(value)
            self._assignments.append((cv, token))
        return self

    def __exit__(self, *exc: Any) -> None:
        for cv, token in reversed(self._assignments):
            try:
                cv.reset(token)
            except ValueError:
                pass
        self._assignments.clear()


# ─── 从 ContextVar 链解析字段 ───────────────────────────────────────────────

def resolve_from_context(
    field: str,
    *,
    principal_var: Optional[ContextVar] = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """从 ContextVar → domain principal 链中解析字段（tenant_id / role 等）。

    查找顺序：
    1. ``principal_var.get().<field>``（如果 principal_var 已设置）
    2. ``domain.principal.get_principal().<field>``（向后兼容）
    3. 返回 fallback

    典型用法::

        tenant_id = resolve_from_context("tenant_id", fallback="default")
    """
    # 1. 从 ContextVar 解析
    if principal_var is not None:
        try:
            p = principal_var.get(None)
            if p is not None:
                val = getattr(p, field, None)
                if val:
                    return val
        except Exception:
            pass

    # 2. 从 domain.principal 解析（向后兼容）
    try:
        from agent_platform.domain.principal import get_principal
        val = getattr(get_principal(), field, None)
        if val:
            return val
    except Exception:
        pass

    return fallback


# ─── 结构化异常日志装饰器 ────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable[..., Any])


def logged_errors(
    event: str,
    *,
    fallback: Any = _SENTINEL,
    reraise: bool = True,
    level: int = logging.WARNING,
    logger_name: Optional[str] = None,
    on_success: Optional[Callable[[Any], Optional[Dict[str, Any]]]] = None,
    on_error: Optional[Callable[[Exception], Optional[Dict[str, Any]]]] = None,
    success_level: int = logging.INFO,
) -> Callable[[F], F]:
    """捕获异常并以 stable_json 格式写入结构化日志；可选的成功回调。

    替代常见的::

        try:
            result = do_something()
        except Exception as e:
            logger.warning(stable_json({"event": "xxx_failed", "error": str(e)}))
            raise

    用法::

        @logged_errors("openai_call_failed")
        def call_openai(...): ...

        # 有 fallback 值（不 reraise）：
        @logged_errors("fetch_data_failed", fallback=None, reraise=False)
        def fetch_data(...): ...

    成功日志::
        @logged_errors(
            "recap_backtest_error",
            on_success=lambda _r: {"event": "scheduler_done", "job": "recap_backtest"},
        )
        def backtest_handler(settings): ...
    """
    def decorator(fn: F) -> F:
        _logger = logging.getLogger(logger_name or fn.__module__)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
                if on_success is not None:
                    extra = on_success(result)
                    if extra is not None:
                        _logger.log(success_level, stable_json(extra))
                return result
            except Exception as e:
                error_payload: Dict[str, Any] = {"event": event, "error": str(e)[:500]}
                if on_error is not None:
                    extra = on_error(e)
                    if extra is not None:
                        error_payload.update(extra)
                _logger.log(level, stable_json(error_payload))
                if reraise:
                    raise
                if fallback is _SENTINEL:
                    return None
                return fallback

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "contextvars_block",
    "logged_errors",
    "resolve_from_context",
    "stable_json",
    "today_str",
    "utc_now_iso",
]
