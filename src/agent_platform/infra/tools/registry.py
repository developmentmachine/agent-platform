"""W2 起，本模块不再持有第二份 schema/handler — 转为 ``tools_server.registry`` 的薄壳。

对外语义不变（为兼容 ``mcp_stdio`` 等调用方）：
- ``TOOL_SCHEMAS``     从 ``tools_server.registry`` 推导（OpenAI tool-calling 兼容格式）
- ``ALL_TOOL_NAMES``   同源派生
- ``execute_tool``     调用 ``InProcessMcpClient`` 同步执行；行为与旧实现一致
- ``prefetch_for_prompt`` 同上

新代码请直接使用 ``runtime.McpToolGateway``，**不要 import 本模块**。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("agent_platform.infra.tools.registry")


def _registry():
    from agent_platform.tools_server.registry import build_default_registry

    return build_default_registry()


def _client():
    from agent_platform.infra.mcp_client.inproc import InProcessMcpClient

    return InProcessMcpClient()


def _all_tool_names() -> tuple:
    return tuple(_registry().names())


def _all_schemas() -> List[Dict[str, Any]]:
    return [spec.to_openai_function() for spec in _registry().list()]


def __getattr__(name: str):
    # Lazy attributes — break the import cycle with tools_server.tools.* shims.
    if name == "ALL_TOOL_NAMES":
        return _all_tool_names()
    if name == "TOOL_SCHEMAS":
        return _all_schemas()
    raise AttributeError(name)


def execute_tool(name: str, arguments: Dict[str, Any], db_path: str = ":memory:") -> str:
    """根据工具名执行对应 handler，返回字符串结果。

    db_path 参数保留只为旧调用方兼容；``query_history`` handler 自行从环境变量解析。
    """
    from agent_platform.observability.runtime_context import current_run_context
    from agent_platform.observability.tracing import get_tracer

    logger.info("tool_call name=%s args=%s", name, arguments)
    ctx = current_run_context.get()
    tracer = get_tracer(__name__)
    attrs: Dict[str, Any] = {"tool.name": name}
    if ctx is not None:
        attrs["recap.request_id"] = ctx.request_id
        attrs["recap.trace_id"] = ctx.trace_id

    with tracer.start_as_current_span("llm.tool.execute", attributes=attrs):
        cli = _client()
        result = cli.call_sync(name, arguments)
    if result.is_error:
        return result.content or f"未知工具: {name}"
    return result.content or ""


def prefetch_for_prompt(
    date: str,
    db_path: str = ":memory:",
    enabled_tools: Optional[Iterable[str]] = None,
) -> str:
    """按 ``enabled_tools`` 预执行工具并拼接上下文。"""
    allowed = set(_all_tool_names()) if enabled_tools is None else set(enabled_tools)
    cli = _client()
    parts: List[str] = []

    if "web_search" in allowed:
        r = cli.call_sync(
            "web_search",
            {"query": f"A股行情 {date} 上证指数 北向资金 板块"},
        )
        parts.append(f"【联网搜索结果】\n{r.content}")
    if "query_market_data" in allowed:
        for dt in ("index", "sector", "northbound"):
            r = cli.call_sync("query_market_data", {"data_type": dt, "date": date})
            parts.append(f"【{dt} 行情数据】\n{r.content}")
    if "query_history" in allowed:
        r = cli.call_sync("query_history", {"mode": "daily", "limit": 3})
        parts.append(f"【近期历史复盘】\n{r.content}")

    return "\n\n".join(parts)


__all__ = [
    "ALL_TOOL_NAMES",
    "TOOL_SCHEMAS",
    "execute_tool",
    "prefetch_for_prompt",
]
