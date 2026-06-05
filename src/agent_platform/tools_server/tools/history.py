"""query_history 工具规格。

handler 需要 ``db_path``，由 ``InProcessMcpClient`` 或 ``server.py`` 在调用时注入
（从 ``RECAP_DB_PATH`` 环境变量或当前 settings 读取）。
"""
from __future__ import annotations

import os

from agent_platform.infra.tools.handlers.history import run_query_history
from agent_platform.tools_server.registry import ToolSpec


def _resolve_db_path() -> str:
    return os.environ.get("RECAP_DB_PATH", "recap_system.db")


def _call(mode: str = "daily", limit: int = 5) -> str:
    return run_query_history(_resolve_db_path(), mode, int(limit))


SPEC = ToolSpec(
    name="query_history",
    description="查询项目内部历史复盘记录，用于对比今日与近期市场走势。",
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["daily", "strategy"],
                "description": "daily=日终复盘, strategy=次日策略",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，默认 5",
                "default": 5,
            },
        },
        "required": ["mode"],
    },
    handler=_call,
    read_only=True,
)


__all__ = ["SPEC"]
