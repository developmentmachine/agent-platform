"""端口（Port）契约：所有跨层依赖都应面向这里的 Protocol，而非具体实现。

实现这些 Port 的代码住在 infrastructure 层；
驱动这些 Port 的代码住在 runtime 层与各 agent 包。
"""
from agent_platform.core.ports.llm import LlmBackendPort
from agent_platform.core.ports.mcp_tool import (
    McpClientPort,
    McpToolDescriptor,
    McpToolResult,
)
from agent_platform.core.ports.memory import EmbeddingsPort, VectorStorePort
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.ports.repository import (
    JobRepository,
    PushLogRepository,
    PromptVersionRepository,
    ToolInvocationRepository,
)
from agent_platform.core.ports.renderer import RendererPort
from agent_platform.core.ports.guardrail import GuardrailPort, GuardrailDecision, GuardrailError
from agent_platform.core.ports.push import PushPort, PushResult
from agent_platform.core.ports.session import SessionResolverPort
from agent_platform.core.ports.metrics import MetricsPort, configure_metrics_port

__all__ = [
    "LlmBackendPort",
    "McpClientPort",
    "McpToolDescriptor",
    "McpToolResult",
    "EmbeddingsPort",
    "VectorStorePort",
    "RepositoryFactoryPort",
    "JobRepository",
    "PushLogRepository",
    "PromptVersionRepository",
    "ToolInvocationRepository",
    "RendererPort",
    "GuardrailPort",
    "GuardrailDecision",
    "GuardrailError",
    "PushPort",
    "PushResult",
    "SessionResolverPort",
    "MetricsPort",
    "configure_metrics_port",
]
