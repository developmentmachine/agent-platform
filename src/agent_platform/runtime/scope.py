"""运行期 Agent 作用域 — 在调用栈上挂载 ``AgentScope``。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from agent_platform.core.registry.agent_definition import AgentDefinition
from agent_platform.core.registry.agent_registry import AgentRegistry, get_default_registry
from agent_platform.core.runtime.agent_scope import AgentScope, current_agent_scope


@contextmanager
def agent_execution(defn: AgentDefinition) -> Iterator[AgentScope]:
    """在 with 块内为当前线程设置 ``AgentScope``（MCP / skill overlay 据此裁剪）。"""
    scope = AgentScope.from_definition(defn)
    token = current_agent_scope.set(scope)
    try:
        yield scope
    finally:
        current_agent_scope.reset(token)


@contextmanager
def agent_execution_for_id(
    agent_id: str,
    registry: Optional[AgentRegistry] = None,
) -> Iterator[AgentScope]:
    """按 ``agent_id`` 从注册表取定义并激活作用域。"""
    reg = registry or get_default_registry()
    with agent_execution(reg.get(agent_id)) as scope:
        yield scope


def require_agent_scope() -> AgentScope:
    """返回当前 ``AgentScope``；未激活时抛错。"""
    scope = current_agent_scope.get()
    if scope is None:
        raise RuntimeError(
            "no active AgentScope: use agent_execution() / AgentRuntime.run() / "
            "create_runtime() paths that activate scope before tools or skill overlay"
        )
    return scope


__all__ = [
    "agent_execution",
    "agent_execution_for_id",
    "require_agent_scope",
]
