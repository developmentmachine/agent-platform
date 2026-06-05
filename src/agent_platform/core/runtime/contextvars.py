"""平台级 ContextVar 集中处 — 兼容老路径的同时提供 ``current_principal``。

``current_run_context`` / ``current_budget`` 直接 re-export 老实现，确保 tool runner
与 LLM provider 不变；``current_principal`` 是新增的请求级 principal slot。
"""
from __future__ import annotations

import contextvars
from typing import Optional

from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.runtime.observability.runtime_context import (  # noqa: F401
    current_budget,
    current_run_context,
)
from agent_platform.core.runtime.agent_scope import current_agent_scope  # noqa: F401

current_principal: contextvars.ContextVar[Optional[PrincipalContext]] = contextvars.ContextVar(
    "agent_platform_principal",
    default=None,
)

__all__ = ["current_run_context", "current_budget", "current_principal", "current_agent_scope"]
