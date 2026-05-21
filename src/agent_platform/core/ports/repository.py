"""Repository 工厂 Port — 平台内核只依赖工厂，不依赖具体 DB。

现有具体仓储 Protocol（``RunRepository`` / ``FeedbackRepository`` / ...）保留在
``agent_platform.domain.repositories`` 以保兼容；本工厂用于在 Composition Root
统一装配。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RepositoryFactoryPort(Protocol):
    """按需创建仓储；不同后端（SQLite / Postgres / InMemory）实现同一接口。"""

    def run_repository(self) -> Any:
        ...

    def feedback_repository(self) -> Any:
        ...

    def evolution_repository(self) -> Any:
        ...

    def backtest_repository(self) -> Any:
        ...

    def tool_invocation_repository(self) -> Any:
        ...
