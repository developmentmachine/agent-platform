"""AgentRuntime — 与 adapters 交互的唯一对象。

职责：
- ``run`` / ``stream``：按 ``agent_id`` 从 registry 取 ``AgentDefinition``，
  完成 principal / session / trace_id 注入，调用其 ``pipeline_factory`` /
  ``chat_handler`` / ``runner`` 之一；
- ``shutdown``：清理 disposers（MCP 子进程、连接池等）。

对应 ares-pkx ``AgentRuntime`` 的 Python 实现；保持 surface 极简，所有装配
都收口到 ``create_runtime``（含 ``mcp_tool_names`` / ``skills`` 依赖校验，在
注册表 ``register`` 阶段完成，本类 ``run`` / ``stream`` 不再校验）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

from agent_platform.core.errors import AgentNotFound
from agent_platform.core.orchestration.side_effects_bus import SideEffectBus
from agent_platform.core.ports.guardrail import GuardrailPort
from agent_platform.core.ports.mcp_tool import McpClientPort
from agent_platform.core.ports.session import SessionResolverPort
from agent_platform.core.registry.agent_definition import (
    AgentDefinition,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
)
from agent_platform.core.registry.agent_registry import AgentRegistry
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.session import SessionContext
from agent_platform.runtime.scope import agent_execution

logger = logging.getLogger("agent_platform.runtime.agent_runtime")

Disposer = Callable[[], None]


@dataclass
class AgentRuntimeOverrides:
    """允许 apps / 测试在 composition root 之外替换某些组件。"""

    session_resolver: Optional[SessionResolverPort] = None
    mcp_client: Optional[McpClientPort] = None
    guardrail: Optional[GuardrailPort] = None
    side_effects: Optional[SideEffectBus] = None
    extra_registrants: List[Callable[[AgentRegistry], None]] = field(default_factory=list)


class AgentRuntime:
    """跨所有入口（CLI / HTTP / WeCom / QQ / Scheduler / MCP）共用的运行时。"""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        session_resolver: SessionResolverPort,
        side_effects: SideEffectBus,
        settings: Any,
        mcp_client: Optional[McpClientPort] = None,
        guardrail: Optional[GuardrailPort] = None,
        disposers: Optional[List[Disposer]] = None,
    ) -> None:
        self._registry = registry
        self._session_resolver = session_resolver
        self._bus = side_effects
        self._settings = settings
        self._mcp_client = mcp_client
        self._guardrail = guardrail
        self._disposers: List[Disposer] = list(disposers or [])

    # ─── meta ─────────────────────────────────────────────────────────────

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    @property
    def side_effects(self) -> SideEffectBus:
        return self._bus

    @property
    def settings(self) -> Any:
        return self._settings

    def list_agents(self) -> List[AgentDefinition]:
        return self._registry.list()

    def add_disposer(self, fn: Disposer) -> None:
        self._disposers.append(fn)

    # ─── core entrypoints ─────────────────────────────────────────────────

    def run(
        self,
        *,
        agent_id: str,
        payload: Dict[str, Any],
        principal: PrincipalContext,
        conversation_key: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> AgentResponseEnvelope:
        defn, session, run_ctx = self._prepare(agent_id, principal, conversation_key, trace_id)
        run_ctx = run_ctx.with_overrides(agent_id=agent_id)
        with agent_execution(defn):
            if defn.runner is not None:
                return defn.runner(
                    envelope=AgentRequestEnvelope(agent_id=agent_id, payload=payload, stream=False),
                    principal=principal,
                    session=session,
                    run_ctx=run_ctx,
                    settings=self._settings,
                    runtime=self,
                )
            if defn.chat_handler is not None:
                out = defn.chat_handler(
                    request=defn.request_model.model_validate(payload),
                    principal=principal,
                    session=session,
                    run_ctx=run_ctx,
                    settings=self._settings,
                    runtime=self,
                )
                return self._wrap_response(defn, run_ctx, out)
            if defn.pipeline_factory is not None:
                raise NotImplementedError(
                    "pipeline-based agents must implement their own ``runner`` to drive the "
                    "Pipeline + RunState (stock-recap migration pending in follow-up commit)"
                )
            raise AgentNotFound(f"agent {agent_id!r} has no callable entrypoint")

    def stream(
        self,
        *,
        agent_id: str,
        payload: Dict[str, Any],
        principal: PrincipalContext,
        conversation_key: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        defn, session, run_ctx = self._prepare(agent_id, principal, conversation_key, trace_id)
        run_ctx = run_ctx.with_overrides(agent_id=agent_id)
        if defn.runner is None:
            raise NotImplementedError(
                f"agent {agent_id!r} does not support streaming (no ``runner`` defined)"
            )
        with agent_execution(defn):
            yield from defn.runner(
                envelope=AgentRequestEnvelope(agent_id=agent_id, payload=payload, stream=True),
                principal=principal,
                session=session,
                run_ctx=run_ctx,
                settings=self._settings,
                runtime=self,
            )

    # ─── lifecycle ────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        for fn in reversed(self._disposers):
            try:
                fn()
            except Exception as e:
                logger.warning("disposer failed: %s", e)
        self._disposers.clear()

    # ─── helpers ──────────────────────────────────────────────────────────

    def _prepare(
        self,
        agent_id: str,
        principal: PrincipalContext,
        conversation_key: Optional[str],
        trace_id: Optional[str],
    ):
        defn = self._registry.get(agent_id)
        conv_key = conversation_key or f"{principal.source}:{principal.subject}"
        session = self._session_resolver.resolve(principal, conv_key)
        run_ctx = RunContext.new(
            session_id=session.session_id,
            mode=None,
            provider=None,
            tenant_id=principal.tenant_id,
        )
        if trace_id:
            run_ctx = run_ctx.__class__(  # type: ignore[call-arg]
                request_id=run_ctx.request_id,
                trace_id=trace_id,
                span_id=run_ctx.span_id,
                session_id=run_ctx.session_id,
                mode=run_ctx.mode,
                provider=run_ctx.provider,
                tenant_id=run_ctx.tenant_id,
            )
        return defn, session, run_ctx

    def _wrap_response(
        self, defn: AgentDefinition, run_ctx: RunContext, out: Any
    ) -> AgentResponseEnvelope:
        if isinstance(out, AgentResponseEnvelope):
            return out
        if hasattr(out, "model_dump"):
            payload = out.model_dump()
        elif isinstance(out, dict):
            payload = out
        else:
            payload = {"result": out}
        return AgentResponseEnvelope(
            agent_id=defn.id,
            request_id=run_ctx.request_id,
            payload=payload,
        )


__all__ = ["AgentRuntime", "AgentRuntimeOverrides", "Disposer"]
