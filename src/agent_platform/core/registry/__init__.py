"""Agent 注册表 — 平台唯一的「Agent 入口」。

发现机制（与 ``skills.loader`` 同模式）：
1. 内置 Agent：各 agent 包的 ``manifest:register`` 在导入时被显式调用；
2. 第三方 Agent：在 ``pyproject.toml`` 登记 entry-point::

      [project.entry-points."agent_platform.agents"]  # noqa
      my_agent = "my_pkg.manifest:register"

CLI / HTTP / Scheduler / Bot 启动时只需 ``discover()``，不再硬编码 AGENTS 字典。
"""
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
    PipelineFactory,
    ScheduledJob,
)
from agent_platform.core.registry.agent_registry import (
    AgentRegistry,
    discover_agents,
    get_default_registry,
)

__all__ = [
    "AgentCapability",
    "AgentDefinition",
    "AgentRequestEnvelope",
    "AgentResponseEnvelope",
    "PipelineFactory",
    "ScheduledJob",
    "AgentRegistry",
    "discover_agents",
    "get_default_registry",
]
