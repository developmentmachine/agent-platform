"""AgentApp — 独立 Agent 启动器。

允许子 agent 在没有 monolith 的情况下独立运行。

用法::

    from agent_platform.core.app import AgentApp

    app = AgentApp(
        agent_id="my-agent",
        repo_factory=SqliteRepositoryFactory(":memory:"),
        llm=llm_backend_effective(),
    )
    result = app.run(payload={"question": "hello"})
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

from agent_platform.config.settings import Settings, get_settings
from agent_platform.core.ports.guardrail import GuardrailPort
from agent_platform.core.ports.llm import LlmBackendPort
from agent_platform.core.ports.push import PushPort
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.registry.agent_definition import (
    AgentDefinition,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
)
from agent_platform.core.registry.agent_registry import AgentRegistry
from agent_platform.core.runtime.agent_scope import agent_execution
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.domain.run_context import RunContext
from agent_platform.core.runtime.session import SessionContext

logger = logging.getLogger("agent_platform.core.app")


@dataclass
class AgentApp:
    """轻量级 Agent 运行容器 — 不依赖 monolith 的 adapters/runtime。

    只需要 core + infra 实现即可运行任意已注册的 agent。
    """

    agent_id: str
    repo_factory: Optional[RepositoryFactoryPort] = None
    llm: Optional[LlmBackendPort] = None
    guardrail: Optional[GuardrailPort] = None
    push: Optional[PushPort] = None
    settings: Optional[Settings] = None
    registry: Optional[AgentRegistry] = None
    _defn: Optional[AgentDefinition] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        if self.registry is None:
            self.registry = AgentRegistry()
            self._discover_agents()

    def _discover_agents(self) -> None:
        """通过 entry_points 发现已安装的 agent。"""
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="agent_platform.agents")
            for ep in eps:
                try:
                    register = ep.load()
                    register(self.registry)
                except Exception as e:
                    logger.debug("agent %s failed to register: %s", ep.name, e)
        except Exception as e:
            logger.debug("entry_points discovery failed: %s", e)

    def _get_definition(self) -> AgentDefinition:
        if self._defn is None:
            self._defn = self.registry.get(self.agent_id)
        return self._defn

    def run(
        self,
        payload: Dict[str, Any],
        *,
        stream: bool = False,
        principal: Optional[PrincipalContext] = None,
    ) -> Any:
        """同步执行 agent。

        Returns:
            AgentResponseEnvelope (non-stream) or Iterator (stream)
        """
        defn = self._get_definition()
        principal = principal or PrincipalContext.anonymous("cli")
        run_ctx = RunContext.new(
            session_id=f"standalone-{uuid.uuid4().hex[:8]}",
            agent_id=self.agent_id,
        )

        envelope = AgentRequestEnvelope(
            agent_id=self.agent_id,
            payload=payload,
            stream=stream,
        )

        with agent_execution(defn):
            return defn.runner(
                envelope=envelope,
                principal=principal,
                session=SessionContext(),
                run_ctx=run_ctx,
                settings=self.settings,
                runtime=self,
            )

    def run_stream(
        self,
        payload: Dict[str, Any],
        *,
        principal: Optional[PrincipalContext] = None,
    ) -> Iterator[Any]:
        """流式执行 agent。"""
        return self.run(payload, stream=True, principal=principal)

    # ── Port 访问（供 agent runner 内部使用） ──

    def get_repo_factory(self) -> Optional[RepositoryFactoryPort]:
        return self.repo_factory

    def get_llm(self) -> Optional[LlmBackendPort]:
        return self.llm

    def get_guardrail(self) -> Optional[GuardrailPort]:
        return self.guardrail

    def get_push(self) -> Optional[PushPort]:
        return self.push


__all__ = ["AgentApp"]
