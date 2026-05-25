"""平台运行时上下文类型（与具体编排无关）。

为保兼容，``RunContext`` 与 ``AgentBudget`` 仍从原 ``domain.run_context`` /
``application.orchestration.budget`` 处 re-export；新增的 ``PrincipalContext`` /
``SessionContext`` / ``ContextVars`` 则首次定义在本子包。
"""
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.principal import PrincipalContext, PrincipalSource
from agent_platform.core.runtime.session import SessionContext
from agent_platform.core.runtime.budget import AgentBudget
from agent_platform.core.runtime.contextvars import current_run_context, current_budget, current_principal

__all__ = [
    "RunContext",
    "PrincipalContext",
    "PrincipalSource",
    "SessionContext",
    "AgentBudget",
    "current_run_context",
    "current_budget",
    "current_principal",
]
