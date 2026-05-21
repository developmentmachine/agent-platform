"""StdioMcpClient — 本地子进程实现，启动 ``agent_platform.tools_server.server`` 或任意
第三方 MCP server。

为什么先做 stdio：
- 零网络依赖；开发与单进程部署默认；
- 与 Cursor Desktop / Claude Desktop 同协议，便于复用；
- 后续 ``HttpMcpClient`` / ``MultiMcpRouter`` 接入时，``McpToolGateway`` 不变。

当前为最小可用实现：``list_tools`` / ``call`` / ``close`` 协议契合
``McpClientPort``，内部直接复用官方 ``mcp.client.stdio`` 异步客户端。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from agent_platform.core.ports.mcp_tool import (
    McpClientPort,
    McpToolDescriptor,
    McpToolResult,
)

logger = logging.getLogger("agent_platform.infra.mcp_client.stdio")


class StdioMcpClient(McpClientPort):
    """通过 stdio 启动并通信的 MCP server 客户端。

    ``command`` / ``args`` / ``env`` 直接对应 MCP 规范的 stdio transport 参数；
    例如启动本仓库自带的 MCP server::

        StdioMcpClient(command="agent_platform-stock-recap-mcp")

    或者第三方 MCP server::

        StdioMcpClient(command="npx", args=["-y", "@xxx/mcp-server"])
    """

    def __init__(
        self,
        *,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        server_id: str = "default",
    ) -> None:
        self._command = command
        self._args = list(args or [])
        self._env = dict(env or {})
        self._server_id = server_id
        self._session: Any = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        if self._session is not None:
            return
        async with self._lock:
            if self._session is not None:
                return
            # 延迟导入：``mcp`` 在测试环境可能未充分初始化
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore

            params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=self._env or None,
            )
            ctx = stdio_client(params)
            self._read_stream, self._write_stream = await ctx.__aenter__()
            self._exit_ctx = ctx
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

    async def list_tools(self) -> List[McpToolDescriptor]:
        await self._ensure_connected()
        resp = await self._session.list_tools()
        out: List[McpToolDescriptor] = []
        for tool in getattr(resp, "tools", []) or []:
            out.append(
                McpToolDescriptor(
                    name=getattr(tool, "name", "") or "",
                    description=getattr(tool, "description", "") or "",
                    input_schema=getattr(tool, "inputSchema", {}) or {},
                    server_id=self._server_id,
                    read_only=True,
                )
            )
        return out

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
        await self._ensure_connected()
        try:
            if timeout_s and timeout_s > 0:
                result = await asyncio.wait_for(
                    self._session.call_tool(name, arguments), timeout=timeout_s
                )
            else:
                result = await self._session.call_tool(name, arguments)
        except asyncio.TimeoutError as e:
            return McpToolResult(
                name=name,
                content=f"timeout after {timeout_s}s",
                is_error=True,
                meta={"error_kind": "timeout"},
            )
        except Exception as e:
            return McpToolResult(
                name=name,
                content=str(e),
                is_error=True,
                meta={"error_kind": "transport"},
            )

        # MCP 工具结果通常是 ContentBlock 列表；这里串成纯文本，复杂结构保留在 meta
        parts: List[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
        return McpToolResult(
            name=name,
            content="\n".join(parts) if parts else "",
            is_error=bool(getattr(result, "isError", False)),
            meta={"server_id": self._server_id},
        )

    async def close(self) -> None:
        if self._session is None:
            return
        try:
            await self._session.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("mcp session close failed: %s", e)
        try:
            await self._exit_ctx.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("mcp transport close failed: %s", e)
        self._session = None
        self._read_stream = None
        self._write_stream = None


__all__ = ["StdioMcpClient"]
