"""AgentDefinition — 一个 Agent 在平台上注册的全部元数据。

设计原则：
- 不限制 Agent 内部如何编排（可以是 Pipeline、可以是直接 LLM 调用、可以是 ReAct）；
- 必须声明 ``request_model`` / ``response_model``，让 adapters 自动反序列化；
- 通过 ``capabilities`` 声明能力，便于路由（"recap/daily" "chat" 等）；
- 通过 ``mcp_tool_names`` 显式声明依赖的 MCP 工具，runtime 启动时校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel


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
    # 声明依赖（runtime 启动时校验）
    mcp_tool_names: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    renderers: List[str] = field(default_factory=list)
    # 给 CLI / 路由 / LLM 看的简短描述
    cli_help: Optional[str] = None
    http_path_prefix: Optional[str] = None


__all__ = [
    "AgentCapability",
    "AgentDefinition",
    "AgentRequestEnvelope",
    "AgentResponseEnvelope",
    "PipelineFactory",
]
