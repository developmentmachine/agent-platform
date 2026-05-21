"""MCP 工具客户端 Port — 平台只通过该协议访问工具，禁止本地 function-calling 注册表。

实现位置：``agent_platform.infra.mcp_client.{stdio,http,router,pool}``。
统一治理（白名单 / 角色 / per-tool budget / 审计 / 超时）由 ``runtime.McpToolGateway``
在 Port 外围包装，保证不同实现共用同一套治理语义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class McpToolDescriptor:
    """单个 MCP 工具元数据。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    server_id: str = "default"
    read_only: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class McpToolResult:
    """工具执行结果。``content`` 为序列化文本（与 MCP 规范一致），``meta`` 为可选附加。"""

    name: str
    content: str
    is_error: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class McpClientPort(Protocol):
    """与 1..N 个 MCP server 通讯的最小抽象（async-friendly，但保留同步入口便于过渡）。"""

    async def list_tools(self) -> List[McpToolDescriptor]:
        ...

    async def call(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        request_id: Optional[str] = None,
        principal_role: Optional[str] = None,
        tenant_id: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> McpToolResult:
        ...

    async def close(self) -> None:
        ...
