"""平台级 ContextVar 集中 re-export。

``current_run_context`` / ``current_budget`` 仍由 observability 模块持有槽位；
``current_principal`` 与 ``PrincipalContext`` 定义在 ``core.runtime.principal``。
"""
from __future__ import annotations

from agent_platform.core.runtime.principal import (  # noqa: F401
    PrincipalContext,
    current_principal,
    get_principal,
    set_principal,
)
from agent_platform.runtime.observability.runtime_context import (  # noqa: F401
    current_budget,
    current_run_context,
)

__all__ = [
    "PrincipalContext",
    "current_run_context",
    "current_budget",
    "current_principal",
    "get_principal",
    "set_principal",
]
