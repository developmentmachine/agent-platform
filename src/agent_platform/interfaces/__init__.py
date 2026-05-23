"""Backward-compat shim (canonical: ``agent_platform.adapters``)."""
from __future__ import annotations

import importlib
from typing import Any

_ALIASES = {
    "cli": "agent_platform.adapters.cli.main",
    "mcp_stdio": "agent_platform.adapters.mcp_stdio.main",
}


def __getattr__(name: str) -> Any:
    if name == "api":
        return importlib.import_module("agent_platform.adapters.http.api")
    if name in _ALIASES:
        return importlib.import_module(_ALIASES[name])
    if name == "scheduler":
        return importlib.import_module("agent_platform.adapters.scheduler")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
