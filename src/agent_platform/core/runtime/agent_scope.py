"""AgentScope — 单次 Agent 执行期的 skill / MCP 白名单（运行期唯一裁剪依据）。"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from agent_platform.core.registry.agent_definition import AgentDefinition
from agent_platform.domain.models import Mode

current_agent_scope: contextvars.ContextVar[Optional["AgentScope"]] = contextvars.ContextVar(
    "agent_platform_agent_scope",
    default=None,
)


@dataclass(frozen=True)
class AgentScope:
    """从 ``AgentDefinition`` 派生的运行期作用域。

    - **MCP**：``mcp_tool_names`` 与全局 ``tools_server`` 求交后才暴露给 LLM / execute；
    - **Skill 选用**：仅 ``skill_mode_map`` + ``skill_ids``，不使用全局合并的 mode 表；
    - **Skill 正文**：``load_skill_document`` 仍走全局 skill 目录（多 bundle 合并），id 须在
      ``skill_ids`` 内才允许 overlay。
    """

    agent_id: str
    mcp_tool_names: FrozenSet[str]
    skill_ids: FrozenSet[str]
    skill_mode_map: Dict[str, str]
    skill_bundle: Optional[str] = None

    @classmethod
    def from_definition(cls, defn: AgentDefinition) -> AgentScope:
        return cls(
            agent_id=defn.id,
            mcp_tool_names=frozenset(defn.mcp_tool_names),
            skill_ids=frozenset(defn.skills),
            skill_mode_map=dict(defn.skill_mode_map),
            skill_bundle=defn.skill_bundle,
        )


def resolve_skill_id_for_agent(
    scope: AgentScope,
    mode: Mode,
    override_skill_id: Optional[str] = None,
) -> Optional[str]:
    """解析本 Agent 在当前 mode 下应加载的 skill id。"""
    sid = (override_skill_id or "").strip() or scope.skill_mode_map.get(mode)
    if not sid:
        return None
    if sid not in scope.skill_ids:
        raise ValueError(
            f"agent {scope.agent_id!r}: skill {sid!r} not in agent skill allowlist "
            f"{sorted(scope.skill_ids)}"
        )
    return sid


# ── Agent 执行期上下文管理 ─────────────────────────────────────────────

from contextlib import contextmanager
from typing import Iterator
from agent_platform.core.registry.agent_registry import AgentRegistry, get_default_registry


@contextmanager
def agent_execution(defn: AgentDefinition) -> Iterator[AgentScope]:
    """在 with 块内为当前线程设置 ``AgentScope``（MCP / skill overlay 据此裁剪）。"""
    scope = AgentScope.from_definition(defn)
    token = current_agent_scope.set(scope)
    try:
        yield scope
    finally:
        try:
            current_agent_scope.reset(token)
        except ValueError:
            current_agent_scope.set(None)


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


__all__ = ["AgentScope", "current_agent_scope", "resolve_skill_id_for_agent",
           "agent_execution", "agent_execution_for_id", "require_agent_scope"]
