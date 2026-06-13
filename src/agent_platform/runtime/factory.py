"""create_runtime — 平台的唯一 Composition Root。

逻辑：
1. 实例化 ``AgentRegistry`` 并执行：
   a. 内置 Agent 的显式 ``register()``（如 stock-recap）；
   b. ``discover_agents()``：第三方包 entry_points；
2. 初始化 SessionResolver（默认 stateless）、SideEffectBus；
3. 注入可选 overrides；
4. 向 ``AgentRegistry`` 注入 ``validate_agent_dependencies``，再 ``register`` 各 Agent；
5. 返回 ``AgentRuntime``（运行期不再校验 ``mcp_tool_names`` / ``skills`` 声明）。
"""
from __future__ import annotations

import logging
from typing import Optional

from agent_platform.config.settings import Settings, get_settings
from agent_platform.core.orchestration.side_effects_bus import SideEffectBus
from agent_platform.core.registry.agent_registry import (
    AgentRegistry,
    discover_agents,
    get_default_registry,
)
from agent_platform.runtime.agent_runtime import AgentRuntime, AgentRuntimeOverrides
from agent_platform.runtime.agent_validation import validate_agent_dependencies
from agent_platform.runtime.session_resolver import StatelessSessionResolver

logger = logging.getLogger("agent_platform.runtime.factory")


def create_runtime(
    settings: Optional[Settings] = None,
    *,
    overrides: Optional[AgentRuntimeOverrides] = None,
    registry: Optional[AgentRegistry] = None,
    auto_discover: bool = True,
    register_builtins: bool = True,
) -> AgentRuntime:
    """实例化 AgentRuntime 并完成注册表装配（含 Agent 依赖声明校验）。"""
    settings = settings or get_settings()
    overrides = overrides or AgentRuntimeOverrides()

    reg = registry or get_default_registry()
    reg.set_dependency_validator(validate_agent_dependencies)

    if register_builtins:
        _register_builtin_agents(reg)

    if auto_discover:
        discover_agents(reg)

    for fn in overrides.extra_registrants:
        try:
            fn(reg)
        except Exception as e:
            logger.warning("extra registrant failed: %s", e)

    session_resolver = overrides.session_resolver or StatelessSessionResolver()
    side_effects = overrides.side_effects or SideEffectBus()

    runtime = AgentRuntime(
        registry=reg,
        session_resolver=session_resolver,
        side_effects=side_effects,
        settings=settings,
        mcp_client=overrides.mcp_client,
        guardrail=overrides.guardrail,
    )
    return runtime


def _register_builtin_agents(reg: AgentRegistry) -> None:
    """通过 entry_points 发现并注册 Agent，editable install 无 entry_point 时回退硬编码列表。

    新增 Agent 只需在 pyproject.toml 声明 entry_point，无需修改本函数。
    """
    from importlib.metadata import entry_points

    try:
        eps = entry_points(group="agent_platform.agents")
        if eps:
            for ep in eps:
                if reg.has(ep.name):
                    continue
                try:
                    register = ep.load()
                    register(reg)
                except Exception as e:
                    logger.warning("failed to register agent %s via entry_point: %s", ep.name, e)
            return
    except Exception as e:
        logger.debug("entry_points(%s) skipped: %s", "agent_platform.agents", e)

    # Fallback: editable install 下 entry_points 可能为空，直接导入 manifest
    logger.debug("no entry_points found, falling back to hardcoded builtin agents")
    _HARDCODED_AGENTS = [
        ("stock_recap", "agent_platform.agents.stock_recap.manifest"),
        ("hsk30_tutor", "agent_platform.agents.hsk30_tutor.manifest"),
    ]
    for name, mod_path in _HARDCODED_AGENTS:
        if reg.has(name):
            continue
        try:
            import importlib

            importlib.import_module(mod_path).register(reg)
        except Exception as e:
            logger.warning("failed to register builtin agent %s: %s", name, e)


def register_builtin_agents(reg: AgentRegistry) -> None:
    """供测试显式装配注册表（与 ``create_runtime(register_builtins=True)`` 一致）。"""
    _register_builtin_agents(reg)


__all__ = ["create_runtime", "register_builtin_agents"]
