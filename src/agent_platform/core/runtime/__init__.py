"""平台运行时上下文类型（与具体编排无关）。

``RunContext`` / ``AgentBudget`` / ``PrincipalContext`` /
``SessionContext`` 与 ContextVar 槽位定义在本子包。
"""
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.principal import (
    PrincipalContext,
    PrincipalSource,
    current_principal,
    get_principal,
    set_principal,
)
from agent_platform.core.runtime.session import SessionContext
from agent_platform.core.runtime.budget import AgentBudget
from agent_platform.core.runtime.contextvars import current_run_context, current_budget

__all__ = [
    "RunContext",
    "PrincipalContext",
    "PrincipalSource",
    "SessionContext",
    "AgentBudget",
    "current_run_context",
    "current_budget",
    "current_principal",
    "get_principal",
    "set_principal",
]
