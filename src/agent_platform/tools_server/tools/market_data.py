"""query_market_data 工具规格。"""
from __future__ import annotations

from typing import Optional

from agent_platform.infrastructure.tools.handlers.market_data import run_query_market_data
from agent_platform.tools_server.registry import ToolSpec


def _call(data_type: str = "index", date: Optional[str] = None) -> str:
    return run_query_market_data(data_type, date)


SPEC = ToolSpec(
    name="query_market_data",
    description="查询 A 股实时/历史行情数据，包括指数、板块涨跌幅、北向资金。",
    input_schema={
        "type": "object",
        "properties": {
            "data_type": {
                "type": "string",
                "enum": ["index", "sector", "northbound"],
                "description": "index=主要指数, sector=板块涨跌, northbound=北向资金",
            },
            "date": {
                "type": "string",
                "description": "查询日期 YYYY-MM-DD，不传则取最新",
            },
        },
        "required": ["data_type"],
    },
    handler=_call,
    read_only=True,
)


__all__ = ["SPEC"]
