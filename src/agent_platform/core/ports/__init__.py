"""端口（Port）契约：所有跨层依赖都应面向这里的 Protocol，而非具体实现。

实现这些 Port 的代码住在 ``agent_platform.infra.*``；
驱动这些 Port 的代码住在 ``agent_platform.runtime`` 与 ``agent_platform.agents.*``。
"""
from agent_platform.core.ports.llm import LlmBackendPort
from agent_platform.core.ports.mcp_tool import (
    McpClientPort,
    McpToolDescriptor,
    McpToolResult,
)
from agent_platform.core.ports.memory import EmbeddingsPort, VectorStorePort
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.ports.renderer import RendererPort
from agent_platform.core.ports.guardrail import GuardrailPort, GuardrailDecision
from agent_platform.core.ports.push import PushPort, PushResult
from agent_platform.core.ports.session import SessionResolverPort

__all__ = [
    "LlmBackendPort",
    "McpClientPort",
    "McpToolDescriptor",
    "McpToolResult",
    "EmbeddingsPort",
    "VectorStorePort",
    "RepositoryFactoryPort",
    "RendererPort",
    "GuardrailPort",
    "GuardrailDecision",
    "PushPort",
    "PushResult",
    "SessionResolverPort",
]
