"""InProcessMcpClient — 进程内 MCP 客户端实现（零子进程开销）。

用途：
- 开发 / 测试 / 单进程部署的默认实现；
- LLM provider 与 tool gateway 都通过 ``McpClientPort`` 调用，行为与
  ``StdioMcpClient`` 完全一致，唯一差别是不跨进程；
- 多租户场景可与 ``HttpMcpClient`` 共存（``MultiMcpRouter`` 路由）。

设计要点：
- 直接读 ``tools_server.registry.build_default_registry()``，避免任何运行时反射；
- 同步 handler 在事件循环中以 ``run_in_executor`` 执行，保证不阻塞调用方；
- 异常一律转 ``McpToolResult(is_error=True)``，与 stdio 实现行为一致。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

from agent_platform.core.ports.mcp_tool import (
    McpClientPort,
    McpToolDescriptor,
    McpToolResult,
)

logger = logging.getLogger("agent_platform.infra.mcp_client.inproc")


if False:  # for type checkers only — runtime 走 lazy import 避免循环
    from agent_platform.tools_server.registry import ToolRegistry  # noqa: F401


class InProcessMcpClient(McpClientPort):
    """进程内运行的 MCP 客户端 — 直接调用 ``tools_server`` 中的 handler。"""

    def __init__(
        self,
        *,
        registry: Optional["ToolRegistry"] = None,
        server_id: str = "inproc",
    ) -> None:
        if registry is None:
            from agent_platform.tools_server.registry import build_default_registry

            registry = build_default_registry()
        self._registry = registry
        self._server_id = server_id

    async def list_tools(self) -> List[McpToolDescriptor]:
        out: List[McpToolDescriptor] = []
        for spec in self._registry.list():
            out.append(
                McpToolDescriptor(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    server_id=self._server_id,
                    read_only=spec.read_only,
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
        if not self._registry.has(name):
            return McpToolResult(
                name=name,
                content=f"unknown tool: {name}",
                is_error=True,
                meta={"error_kind": "not_registered"},
            )
        spec = self._registry.get(name)

        # handler 可能是同步函数；用 to_thread 跑到线程池，可叠加 timeout
        async def _run() -> Any:
            if inspect.iscoroutinefunction(spec.handler):
                return await spec.handler(**arguments)
            return await asyncio.to_thread(spec.handler, **arguments)

        try:
            if timeout_s and timeout_s > 0:
                result = await asyncio.wait_for(_run(), timeout=timeout_s)
            else:
                result = await _run()
        except asyncio.TimeoutError:
            return McpToolResult(
                name=name,
                content=f"timeout after {timeout_s}s",
                is_error=True,
                meta={"error_kind": "timeout"},
            )
        except TypeError as e:
            return McpToolResult(
                name=name,
                content=f"bad arguments: {e}",
                is_error=True,
                meta={"error_kind": "bad_arguments"},
            )
        except Exception as e:
            logger.warning("inproc mcp tool call failed: name=%s err=%s", name, e)
            return McpToolResult(
                name=name,
                content=str(e),
                is_error=True,
                meta={"error_kind": "runtime"},
            )

        return McpToolResult(
            name=name,
            content=result if isinstance(result, str) else str(result),
            is_error=False,
            meta={"server_id": self._server_id},
        )

    async def close(self) -> None:
        # 无外部资源
        return None

    # ─── 同步辅助 ─────────────────────────────────────────────────────────
    # 现有调用方（RecapToolRunner.execute）是同步 API；这里提供同步 sugar
    # 避免每个调用都自行 asyncio.run，且与 ContextVar 兼容。

    def call_sync(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        timeout_s: Optional[float] = None,
    ) -> McpToolResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.call(name, arguments, timeout_s=timeout_s))
        # 已在事件循环里 — 不应同步阻塞。开新线程跑事件循环。
        import threading

        result_box: Dict[str, McpToolResult] = {}

        def _runner() -> None:
            result_box["v"] = asyncio.run(self.call(name, arguments, timeout_s=timeout_s))

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return result_box["v"]

    def list_tools_sync(self) -> List[McpToolDescriptor]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.list_tools())
        import threading

        box: Dict[str, List[McpToolDescriptor]] = {}

        def _runner() -> None:
            box["v"] = asyncio.run(self.list_tools())

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return box["v"]


__all__ = ["InProcessMcpClient"]
