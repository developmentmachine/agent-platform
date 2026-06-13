"""Repository 工厂 Port + 新增仓储 Protocol（Job / PushLog / PromptVersion / ToolInvocation）。

已有的 ``RunRepository`` / ``FeedbackRepository`` / ``EvolutionRepository`` /
``BacktestRepository`` / ``ExperimentRepository`` / ``RecapAuditRepository``
定义在 ``agent_platform.domain.repositories``，此处复用而不重复声明。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from agent_platform.domain.repositories import (
    BacktestRepository,
    EvolutionRepository,
    ExperimentRepository,
    FeedbackRepository,
    RecapAuditRepository,
    RunRepository,
)


# ── 新增 Protocol（domain/repositories.py 中尚未覆盖） ──────────────────────


@runtime_checkable
class JobRepository(Protocol):
    """``jobs`` 表 — 长任务原语：把同步 generate 包成可异步轮询的作业。"""

    def insert(
        self,
        *,
        job_id: str,
        kind: str,
        request_payload: Dict[str, Any],
        tenant_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        status: str = "queued",
        created_at: Optional[str] = None,
    ) -> bool: ...

    def load(self, *, job_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...

    def load_by_idem(
        self, *, tenant_id: Optional[str], idempotency_key: str
    ) -> Optional[Dict[str, Any]]: ...

    def list(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]: ...

    def update_running(
        self,
        *,
        job_id: str,
        request_id: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None: ...

    def mark_done(
        self,
        *,
        job_id: str,
        result_payload: Dict[str, Any],
        request_id: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None: ...

    def mark_failed(
        self,
        *,
        job_id: str,
        error: str,
        request_id: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None: ...


@runtime_checkable
class PushLogRepository(Protocol):
    """``push_log`` 表 — 推送幂等账本。"""

    def get(self, *, request_id: str, channel: str) -> Optional[Dict[str, Any]]: ...

    def upsert(
        self,
        *,
        request_id: str,
        channel: str,
        status: str,
        now_iso: str,
        last_error: Optional[str] = None,
    ) -> None: ...


@runtime_checkable
class PromptVersionRepository(Protocol):
    """``prompt_state`` 表 — 全局活跃 Prompt 版本（单行）。"""

    def get_active(self) -> Optional[str]: ...

    def set_active(self, *, version: str, updated_at: str) -> None: ...


@runtime_checkable
class ToolInvocationRepository(Protocol):
    """``tool_invocations`` 表 — 工具调用审计明细。"""

    def insert(
        self,
        *,
        request_id: Optional[str],
        tool_name: str,
        status: str,
        read_only: bool,
        principal_role: Optional[str],
        arguments: Optional[Dict[str, Any]],
        latency_ms: Optional[int],
        error: Optional[str],
        created_at: str,
        tenant_id: Optional[str] = None,
    ) -> None: ...

    def load_recent(
        self,
        *,
        request_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]: ...


@runtime_checkable
class RepositoryFactoryPort(Protocol):
    """按需创建仓储；不同后端（SQLite / Postgres / InMemory）实现同一接口。"""

    def run_repository(self) -> RunRepository: ...

    def feedback_repository(self) -> FeedbackRepository: ...

    def evolution_repository(self) -> EvolutionRepository: ...

    def backtest_repository(self) -> BacktestRepository: ...

    def tool_invocation_repository(self) -> ToolInvocationRepository: ...

    def job_repository(self) -> JobRepository: ...

    def push_log_repository(self) -> PushLogRepository: ...

    def experiment_repository(self) -> ExperimentRepository: ...

    def recap_audit_repository(self) -> RecapAuditRepository: ...

    def prompt_version_repository(self) -> PromptVersionRepository: ...
