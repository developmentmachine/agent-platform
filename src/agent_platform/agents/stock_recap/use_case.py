"""核心业务逻辑：generate_once。

将数据采集、特征工程、prompt → LLM → 评测、持久化、推送串联。
供 CLI、API、调度器共用；可选 RunContext 与 OpenTelemetry 关联。
"""
from __future__ import annotations

import time
from typing import Iterator, Optional

from opentelemetry import trace

from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState
from agent_platform.agents.stock_recap.legacy_pipeline import (
    execute_recap_pipeline,
    iter_recap_agent_ndjson,
)
from agent_platform.agents.stock_recap.effects.deferred import run_deferred_post_recap
from agent_platform.agents.stock_recap.effects.backtest import try_run_backtest
from agent_platform.config.settings import Settings
from agent_platform.domain.models import GenerateRequest, GenerateResponse
from agent_platform.domain.run_context import RunContext
from agent_platform.core.runtime.contextvars import current_budget, current_run_context
from agent_platform.core.runtime.agent_scope import agent_execution
from agent_platform.core.utils import resolve_from_context
from agent_platform.core.ports.guardrail import GuardrailPort

_RECAP_AGENT_ID = "stock-recap"
from agent_platform.core.runtime.tracing import configure_tracing, get_tracer


def _current_tenant_id() -> Optional[str]:
    """从 ``current_principal`` 取 tenant_id；CLI / 内部调用没有 principal 时返回 None。"""
    return resolve_from_context("tenant_id")


def _resolve_deps(
    guardrail: Optional[GuardrailPort],
    repo_factory=None,
):
    """Resolve deps: use provided values or fall back to default_deps()."""
    from agent_platform.agents.stock_recap.deps import default_deps

    if guardrail is not None and repo_factory is not None:
        return guardrail, repo_factory
    d = default_deps()
    return guardrail or d.guardrail, repo_factory or d.repo_factory


def _resolve_full_deps(guardrail=None, repo_factory=None):
    """Resolve guardrail, repo_factory, and optional callable deps from default_deps()."""
    from agent_platform.agents.stock_recap.deps import default_deps

    d = default_deps()
    gr = guardrail or d.guardrail
    rf = repo_factory or d.repo_factory
    return gr, rf, d.memory_factory, d.llm_caller, d.push_provider_factory


def generate_once(
    req: GenerateRequest,
    settings: Settings,
    ctx: Optional[RunContext] = None,
    *,
    defer_evolution_backtest: bool = False,
    guardrail: Optional[GuardrailPort] = None,
    repo_factory=None,
) -> GenerateResponse:
    """
    单次生成流程：采集 → 特征 → prompt → LLM → 评测 → 持久化 → 推送。
    具体阶段见 ``agents.stock_recap.legacy_pipeline.execute_recap_pipeline``。

    ``defer_evolution_backtest=True`` 时不在本调用内执行进化检查与策略回测（供 HTTP
    层用 BackgroundTasks 延后执行，以缩短响应尾部延迟）；推送仍在请求内完成。
    """
    gr, rf, mem_factory, llm_caller, push_factory = _resolve_full_deps(guardrail, repo_factory)
    configure_tracing(settings)
    gr.validate_generate_request(req)

    from agent_platform.agents.stock_recap.manifest import _build_definition

    with agent_execution(_build_definition()):
        run_ctx = (ctx or RunContext.new()).with_overrides(
            mode=req.mode,
            provider=str(req.provider),
            tenant_id=_current_tenant_id(),
            agent_id=_RECAP_AGENT_ID,
        )
        request_id = run_ctx.request_id
        t0 = time.time()
        ctx_token = current_run_context.set(run_ctx)
        tracer = get_tracer(__name__)

        state = RecapAgentRunState(
            request=req,
            settings=settings,
            run_ctx=run_ctx,
            t0=t0,
            defer_evolution_backtest=defer_evolution_backtest,
            guardrail=gr,
            repo_factory=rf,
            memory_factory=mem_factory,
            llm_caller=llm_caller,
            push_provider_factory=push_factory,
        )
        budget_token = current_budget.set(state.budget)

        try:
            with tracer.start_as_current_span(
                "recap.generate",
                attributes={
                    "recap.request_id": request_id,
                    "recap.trace_id": run_ctx.trace_id,
                    "recap.mode": req.mode,
                    "recap.provider": str(req.provider),
                },
            ):
                if run_ctx.session_id:
                    span = trace.get_current_span()
                    span.set_attribute("recap.session_id", run_ctx.session_id)

                return execute_recap_pipeline(state)
        finally:
            current_budget.reset(budget_token)
            current_run_context.reset(ctx_token)


def iter_generate_ndjson(
    req: GenerateRequest,
    settings: Settings,
    ctx: Optional[RunContext] = None,
    *,
    defer_evolution_backtest: bool = True,
    guardrail: Optional[GuardrailPort] = None,
    repo_factory=None,
) -> Iterator[str]:
    """
    产出 NDJSON 行（``meta``、各 ``phase``、``result``），供 HTTP 流式端点使用。
    若 ``defer_evolution_backtest=True``，在流结束后于当前 worker 内执行进化与回测。

    不在此路径上设置 ``ContextVar``/父 span：``StreamingResponse`` 可能在线程池中
    迭代生成器，跨线程 attach/detach 会失败；``meta``/``result`` 中仍含 request_id。
    """
    gr, rf, mem_factory, llm_caller, push_factory = _resolve_full_deps(guardrail, repo_factory)
    configure_tracing(settings)
    gr.validate_generate_request(req)

    from agent_platform.agents.stock_recap.manifest import _build_definition

    with agent_execution(_build_definition()):
        run_ctx = (ctx or RunContext.new()).with_overrides(
            mode=req.mode,
            provider=str(req.provider),
            tenant_id=_current_tenant_id(),
            agent_id=_RECAP_AGENT_ID,
        )
        request_id = run_ctx.request_id
        t0 = time.time()
        prev_ctx = current_run_context.get()
        current_run_context.set(run_ctx)

        state = RecapAgentRunState(
            request=req,
            settings=settings,
            run_ctx=run_ctx,
            t0=t0,
            defer_evolution_backtest=defer_evolution_backtest,
            guardrail=gr,
            repo_factory=rf,
            memory_factory=mem_factory,
            llm_caller=llm_caller,
            push_provider_factory=push_factory,
        )
        prev_budget = current_budget.get()
        current_budget.set(state.budget)
        try:
            yield from iter_recap_agent_ndjson(state)
        finally:
            current_budget.set(prev_budget)
            current_run_context.set(prev_ctx)
        if (
            defer_evolution_backtest
            and state.stream_pipeline_completed
            and state.snapshot is not None
        ):
            run_deferred_post_recap(
                request_id,
                req.mode,
                state.snapshot.date,
                state.recap is not None,
            )


# 对 cli/scheduler 的后向兼容别名（保持旧导入 `from application.recap import _try_run_backtest` 有效）。
_try_run_backtest = try_run_backtest
