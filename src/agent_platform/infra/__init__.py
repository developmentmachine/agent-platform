"""infra — Driven Adapters：实现 ``core.ports`` 的具体技术细节。

迁移策略（W1/W2）：
- 旧路径 ``agent_platform.infrastructure.*`` 仍为真实源（部分子包已 shim）；
- 本子包通过延迟加载 re-export 子模块，避免 ``infrastructure`` 空 ``__init__`` 导致 AttributeError。
"""
from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = frozenset({"llm", "persistence", "memory", "push"})


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"agent_platform.infrastructure.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["llm", "persistence", "memory", "push"]
