"""create_runtime — 平台的唯一 Composition Root。

逻辑：
1. 实例化 ``AgentRegistry`` 并执行：
   a. 内置 Agent 的显式 ``register()``（如 stock-recap）；
   b. ``discover_agents()``：第三方包 entry_points；
2. 初始化 SessionResolver（默认 stateless）、SideEffectBus；
3. 注入可选 overrides；
4. 返回 ``AgentRuntime``。
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
    """实例化 AgentRuntime 并完成注册表装配。"""
    settings = settings or get_settings()
    overrides = overrides or AgentRuntimeOverrides()

    reg = registry or get_default_registry()

    if register_builtins:
        register_builtin_agents(reg)

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


def register_builtin_agents(reg: AgentRegistry) -> None:
    """显式注册仓库内 Agent（避免 entry_points 在 editable install 下偶发失效）。"""
    try:
        from agent_platform.agents.stock_recap import manifest as stock_recap_manifest

        stock_recap_manifest.register(reg)
    except Exception as e:
        logger.warning("failed to register builtin agent stock_recap: %s", e)
    try:
        from agent_platform.agents.hsk30_tutor import manifest as hsk30_tutor_manifest

        hsk30_tutor_manifest.register(reg)
    except Exception as e:
        logger.warning("failed to register builtin agent hsk30_tutor: %s", e)


_register_builtin_agents = register_builtin_agents  # 内部别名


__all__ = ["create_runtime", "register_builtin_agents"]
