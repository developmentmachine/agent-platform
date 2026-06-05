"""web_search 工具规格。"""
from __future__ import annotations

from agent_platform.infra.tools.handlers.web_search import run_web_search
from agent_platform.tools_server.registry import ToolSpec


def _call(query: str) -> str:
    return run_web_search(query)


SPEC = ToolSpec(
    name="web_search",
    description=(
        "搜索互联网获取实时市场信息，包括今日指数涨跌、板块热点、"
        "北向资金、美股行情、大宗商品、地缘政治等。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，例如：今日上证指数收盘 2024-01-02",
            }
        },
        "required": ["query"],
    },
    handler=_call,
    read_only=True,
)


__all__ = ["SPEC"]
