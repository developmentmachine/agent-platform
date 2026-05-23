"""Backward-compat shim → ``agent_platform.core.domain`` + principal/run_context。"""
from __future__ import annotations

from agent_platform.core.domain import *  # noqa: F403
from agent_platform.core.domain import __all__ as _core_all
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.principal import (
    PrincipalContext,
    current_principal,
    get_principal,
    set_principal,
)

__all__ = list(_core_all) + [
    "RunContext",
    "PrincipalContext",
    "current_principal",
    "get_principal",
    "set_principal",
]
