"""平台级 ContextVar 集中处 — 兼容老路径的同时提供 ``current_principal``。

``current_run_context`` / ``current_budget`` 的实际定义在此模块（从 runtime 层迁入），
确保 core 包自包含；``current_principal`` 是新增的请求级 principal slot。
"""
from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Optional

from agent_platform.domain.run_context import RunContext
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.agent_scope import current_agent_scope  # noqa: F401

if TYPE_CHECKING:
    from agent_platform.core.runtime.budget import AgentBudget

current_run_context: contextvars.ContextVar[Optional[RunContext]] = contextvars.ContextVar(
    "agent_platform_run_context",
    default=None,
)

current_budget: contextvars.ContextVar[Optional["AgentBudget"]] = contextvars.ContextVar(
    "agent_platform_agent_budget",
    default=None,
)

current_principal: contextvars.ContextVar[Optional[PrincipalContext]] = contextvars.ContextVar(
    "agent_platform_principal",
    default=None,
)

__all__ = ["current_run_context", "current_budget", "current_principal", "current_agent_scope"]
