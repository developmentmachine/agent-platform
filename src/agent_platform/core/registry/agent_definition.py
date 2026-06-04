"""AgentDefinition — 一个 Agent 在平台上注册的全部元数据。

设计原则：
- 不限制 Agent 内部如何编排（可以是 Pipeline、可以是直接 LLM 调用、可以是 ReAct）；
- 必须声明 ``request_model`` / ``response_model``，让 adapters 自动反序列化；
- 通过 ``capabilities`` 声明能力，便于路由（"recap/daily" "chat" 等）；
- **运行期裁剪**：``AgentScope``（``current_agent_scope``）在 ``agent_execution`` /
  ``generate_once`` / ``AgentRuntime.run`` 内激活；MCP 暴露 =
  平台工具池 ∩ ``mcp_tool_names``；skill overlay 仅读 ``skill_mode_map`` ∩ ``skills``。
- **注册期校验**：``create_runtime`` 注入 ``validate_agent_dependencies``，在
  ``AgentRegistry.register`` 前核对声明 ⊆ 全局池且与 bundle 一致。
- ``skills`` / ``skill_mode_map`` 用 ``with_skill_bundle`` 推导（skill id 真源：
  ``SKILL.md`` 的 ``name``；``manifest.json`` 只写 ``path``）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class ScheduledJob:
    """单个调度任务声明（W6）。

    Agent manifest 声明 ``scheduled_jobs=[ScheduledJob(...), ...]``；scheduler 装配器
    迭代 ``AgentRegistry`` 自动 ``add_job(handler, CronTrigger(**cron_kwargs))``。
    平台级公共任务（outbox_sweep）保留在 scheduler 自身。
    """

    id: str
    description: str
    cron_kwargs: Dict[str, Any]  # 直接喂给 ``apscheduler.triggers.cron.CronTrigger``
    handler: Callable[[Any], None]  # ``(settings) -> None``
    coalesce: bool = True
    max_instances: int = 1
    replace_existing: bool = True


class AgentCapability(str, Enum):
    """Agent 能力标签：用于路由 / 文档生成。"""

    REPORT = "report"          # 单次报告类（如 stock-recap）
    CHAT = "chat"              # 多轮对话
    STREAMING = "streaming"    # 支持 NDJSON 流
    TOOL_USING = "tool_using"  # 使用 MCP 工具
    SCHEDULED = "scheduled"    # 可被调度器触发


class AgentRequestEnvelope(BaseModel):
    """Adapter → Agent 的统一请求外壳。

    具体业务字段放在 ``payload`` 中，由 Agent 用自己的 ``request_model`` 反序列化。
    """

    agent_id: str
    payload: Dict[str, Any]
    stream: bool = False


class AgentResponseEnvelope(BaseModel):
    """Agent → Adapter 的统一响应外壳。"""

    agent_id: str
    request_id: str
    payload: Dict[str, Any]
    rendered: Dict[str, str] = {}
    errors: List[str] = []


# 注意：Pipeline 是泛型，这里用 Any 而不是 Pipeline[Any]，避免 mypy 抱怨。
PipelineFactory = Callable[[Any], Any]
"""``(settings) -> Pipeline``；Pipeline 内部的 RunState 由 Agent 自己定。"""


@dataclass(frozen=True)
class AgentDefinition:
    """单个 Agent 的注册元数据。"""

    id: str
    display_name: str
    description: str
    request_model: Type[BaseModel]
    response_model: Type[BaseModel]
    capabilities: List[AgentCapability] = field(default_factory=list)
    # 业务入口三选一（按 Agent 风格自选）：
    # 1) pipeline_factory：返回 Pipeline 实例；
    # 2) chat_handler：直接处理 (request, ctx) -> response（适合简单 Agent）；
    # 3) runner：完全自定义（最大灵活度）。
    pipeline_factory: Optional[PipelineFactory] = None
    chat_handler: Optional[Callable[..., Any]] = None
    runner: Optional[Callable[..., Any]] = None
    # 依赖声明（见模块 docstring：由 create_runtime 注入的 register 钩子校验，非 AgentRuntime）
    mcp_tool_names: List[str] = field(default_factory=list)
    # Skill：用 with_skill_bundle() 填充；skill_bundle 为 agent_platform.skills entry point 名
    skill_bundle: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    skill_mode_map: Dict[str, str] = field(default_factory=dict)
    renderers: List[str] = field(default_factory=list)
    # 给 CLI / 路由 / LLM 看的简短描述
    cli_help: Optional[str] = None
    http_path_prefix: Optional[str] = None

    # ── W6: 各装配层钩子（全部 Optional，未填即不挂载） ────────────────────
    # CLI subcommand：(subparser: ArgumentParser) -> None
    cli_subparser_factory: Optional[Callable[[Any], None]] = None
    # CLI subcommand 执行体：(args, settings, subparser) -> int
    cli_run_handler: Optional[Callable[..., int]] = None
    # HTTP FastAPI 路由（lazy 工厂；启动时调用）
    http_router_factories: List[Callable[[], Any]] = field(default_factory=list)
    # 调度任务声明
    scheduled_jobs: List[ScheduledJob] = field(default_factory=list)


__all__ = [
    "AgentCapability",
    "AgentDefinition",
    "AgentRequestEnvelope",
    "AgentResponseEnvelope",
    "PipelineFactory",
    "ScheduledJob",
]
