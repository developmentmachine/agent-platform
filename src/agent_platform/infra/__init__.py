"""infra — Driven Adapters：实现 ``core.ports`` 的具体技术细节。"""
from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = frozenset(
    {"llm", "persistence", "memory", "push", "tools", "mcp_client", "data"}
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"agent_platform.infra.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(_SUBMODULES)
