"""AgentRegistry — 进程内单例注册表 + entry_points 发现。

复用 ``skills.loader`` 已经验证的 entry_points 模式：
- 第三方包通过 ``[project.entry-points."agent_platform.agents"]`` 暴露
  ``module:register`` 可调用，``register(registry)`` 由本注册表在 ``discover()``
  时统一驱动。
"""
from __future__ import annotations

import logging
import threading
from importlib import metadata
from typing import Callable, Dict, List, Optional

from agent_platform.core.errors import AgentNotFound
from agent_platform.core.registry.agent_definition import AgentDefinition

DependencyValidator = Callable[[AgentDefinition], None]

logger = logging.getLogger("agent_platform.core.registry.agent_registry")

ENTRY_POINT_GROUP = "agent_platform.agents"

Registrant = Callable[["AgentRegistry"], None]


class AgentRegistry:
    """线程安全的 Agent 注册表。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: Dict[str, AgentDefinition] = {}
        self._dependency_validator: Optional[DependencyValidator] = None

    def set_dependency_validator(self, validator: Optional[DependencyValidator]) -> None:
        """由 Composition Root（``create_runtime``）注入 skill / MCP 依赖校验。"""
        with self._lock:
            self._dependency_validator = validator

    def register(self, defn: AgentDefinition, *, validate: bool = True) -> None:
        """注册 Agent。``validate=True`` 且已 ``set_dependency_validator`` 时校验依赖。

        正常进程应通过 ``create_runtime`` 装配（会先注入 validator 再 register 内置 Agent）。
        ``AgentRuntime`` 本身不重复校验；``validate=False`` 供单测绕过。
        """
        if validate and self._dependency_validator is not None:
            self._dependency_validator(defn)
        with self._lock:
            if defn.id in self._agents:
                logger.warning("agent already registered, overriding: id=%s", defn.id)
            self._agents[defn.id] = defn

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> AgentDefinition:
        with self._lock:
            try:
                return self._agents[agent_id]
            except KeyError as e:
                raise AgentNotFound(f"unknown agent id: {agent_id}") from e

    def has(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._agents

    def list(self) -> List[AgentDefinition]:
        with self._lock:
            return list(self._agents.values())

    def ids(self) -> List[str]:
        with self._lock:
            return list(self._agents.keys())

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()


_default_registry: Optional[AgentRegistry] = None
_default_lock = threading.RLock()


def get_default_registry() -> AgentRegistry:
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            _default_registry = AgentRegistry()
        return _default_registry


def discover_agents(registry: Optional[AgentRegistry] = None) -> AgentRegistry:
    """从 entry_points 发现所有 Agent，并调用其 ``register(registry)``。

    幂等：同 id 重复注册时由 ``AgentRegistry.register`` 警告并覆盖。
    """
    reg = registry or get_default_registry()
    try:
        eps = metadata.entry_points()
        selected = (
            eps.select(group=ENTRY_POINT_GROUP)
            if hasattr(eps, "select")
            else eps.get(ENTRY_POINT_GROUP, ())
        )
    except Exception as e:
        logger.debug("entry_points(%s) skipped: %s", ENTRY_POINT_GROUP, e)
        return reg

    for ep in selected:
        if reg.has(ep.name):
            continue
        try:
            obj = ep.load()
        except Exception as e:
            logger.warning("failed to load agent entry point %s: %s", ep.name, e)
            continue
        if not callable(obj):
            logger.warning("agent entry point %s is not callable", ep.name)
            continue
        try:
            obj(reg)
        except Exception as e:
            logger.warning("failed to register agent via entry point %s: %s", ep.name, e)
    return reg


__all__ = [
    "AgentRegistry",
    "DependencyValidator",
    "Registrant",
    "ENTRY_POINT_GROUP",
    "discover_agents",
    "get_default_registry",
]
