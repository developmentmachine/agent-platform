"""SqliteRepositoryFactory — implements ``RepositoryFactoryPort``.

在 Composition Root（或测试 conftest）中构造一次，然后注入给 runtime / agent 代码。
"""
from __future__ import annotations

from dataclasses import dataclass

from agent_platform.core.ports.repository import (
    JobRepository,
    PromptVersionRepository,
    PushLogRepository,
    RepositoryFactoryPort,
    ToolInvocationRepository,
)
from agent_platform.domain.repositories import (
    BacktestRepository,
    EvolutionRepository,
    ExperimentRepository,
    FeedbackRepository,
    RecapAuditRepository,
    RunRepository,
)
from agent_platform.infra.persistence.repositories import (
    SqliteBacktestRepository,
    SqliteEvolutionRepository,
    SqliteExperimentRepository,
    SqliteFeedbackRepository,
    SqliteJobRepository,
    SqlitePromptVersionRepository,
    SqlitePushLogRepository,
    SqliteRecapAuditRepository,
    SqliteRunRepository,
    SqliteToolInvocationRepository,
)


@dataclass(frozen=True)
class SqliteRepositoryFactory(RepositoryFactoryPort):
    """SQLite-backed implementation of :class:`RepositoryFactoryPort`."""

    db_path: str

    def run_repository(self) -> RunRepository:
        return SqliteRunRepository(self.db_path)

    def feedback_repository(self) -> FeedbackRepository:
        return SqliteFeedbackRepository(self.db_path)

    def evolution_repository(self) -> EvolutionRepository:
        return SqliteEvolutionRepository(self.db_path)

    def backtest_repository(self) -> BacktestRepository:
        return SqliteBacktestRepository(self.db_path)

    def tool_invocation_repository(self) -> ToolInvocationRepository:
        return SqliteToolInvocationRepository(self.db_path)

    def job_repository(self) -> JobRepository:
        return SqliteJobRepository(self.db_path)

    def push_log_repository(self) -> PushLogRepository:
        return SqlitePushLogRepository(self.db_path)

    def experiment_repository(self) -> ExperimentRepository:
        return SqliteExperimentRepository(self.db_path)

    def recap_audit_repository(self) -> RecapAuditRepository:
        return SqliteRecapAuditRepository(self.db_path)

    def prompt_version_repository(self) -> PromptVersionRepository:
        return SqlitePromptVersionRepository(self.db_path)


__all__ = ["SqliteRepositoryFactory"]
