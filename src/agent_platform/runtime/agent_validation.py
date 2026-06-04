"""Agent 依赖声明校验 — 仅在 ``AgentRegistry.register`` 时调用，非 ``AgentRuntime.run``。

由 ``create_runtime`` 通过 ``AgentRegistry.set_dependency_validator`` 注入本模块的
``validate_agent_dependencies``；直接 ``register`` 且未注入 validator 时不会执行。
"""
from __future__ import annotations

from typing import AbstractSet, Set

from agent_platform.core.errors import AgentDependencyError
from agent_platform.core.registry.agent_definition import AgentDefinition
from agent_platform.skills.bundle import read_bundle_manifest, resolve_skill_bundle_root


def _registered_skill_ids() -> Set[str]:
    from agent_platform.skills.loader import list_registered_skills

    return {str(s["id"]) for s in list_registered_skills() if s.get("id")}


def _registered_tool_names() -> Set[str]:
    from agent_platform.tools_server.registry import build_default_registry

    return set(build_default_registry().names())


def _bundle_manifest_for(defn: AgentDefinition):
    key = defn.skill_bundle
    if not key:
        return None
    root = resolve_skill_bundle_root(key)
    return read_bundle_manifest(root)


def validate_agent_dependencies(defn: AgentDefinition) -> None:
    """校验 Agent 声明的 MCP 工具与 Skill 依赖。

    - ``mcp_tool_names``：每项须在 ``tools_server`` 登记表中存在；
    - ``skills``：每项须在合并后的全局 skill manifest 中存在；
    - ``skill_mode_map``：映射值须为 ``skills`` 的子集；
    - ``skill_bundle``：若设置，``skills`` / ``skill_mode_map`` 须与对应 bundle manifest 一致。
    """
    _validate_mcp_tools(defn, _registered_tool_names())
    _validate_skills(defn, _registered_skill_ids())
    _validate_skill_bundle_consistency(defn)


def _validate_mcp_tools(defn: AgentDefinition, known: AbstractSet[str]) -> None:
    missing = [n for n in defn.mcp_tool_names if n not in known]
    if missing:
        raise AgentDependencyError(
            f"agent {defn.id!r}: unknown mcp_tool_names {missing} (known: {sorted(known)})"
        )


def _validate_skills(defn: AgentDefinition, known: AbstractSet[str]) -> None:
    if not defn.skills and not defn.skill_mode_map and not defn.skill_bundle:
        return
    missing = [s for s in defn.skills if s not in known]
    if missing:
        raise AgentDependencyError(
            f"agent {defn.id!r}: unknown skills {missing} (registered: {sorted(known)})"
        )
    orphan_modes = sorted(set(defn.skill_mode_map.values()) - set(defn.skills))
    if orphan_modes:
        raise AgentDependencyError(
            f"agent {defn.id!r}: skill_mode_map references skills not in skills list: {orphan_modes}"
        )


def _validate_skill_bundle_consistency(defn: AgentDefinition) -> None:
    if not defn.skill_bundle:
        return
    bundle = _bundle_manifest_for(defn)
    if bundle is None:
        return
    declared = tuple(defn.skills)
    if declared != bundle.skill_ids:
        raise AgentDependencyError(
            f"agent {defn.id!r}: skills {list(declared)} diverge from bundle "
            f"{defn.skill_bundle!r} manifest {list(bundle.skill_ids)}; "
            f"use skills.bundle.with_skill_bundle() at register time"
        )
    if dict(defn.skill_mode_map) != bundle.mode_to_skill_id:
        raise AgentDependencyError(
            f"agent {defn.id!r}: skill_mode_map diverges from bundle {defn.skill_bundle!r} "
            f"manifest; use with_skill_bundle()"
        )


__all__ = ["validate_agent_dependencies"]
