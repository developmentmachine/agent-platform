"""MCP 工具实现集合 — 与原 ``infrastructure.tools.handlers`` 同一对象。"""
from agent_platform.infra.tools.handlers.history import run_query_history
from agent_platform.infra.tools.handlers.market_data import run_query_market_data
from agent_platform.infra.tools.handlers.web_search import run_web_search

__all__ = [
    "run_query_history",
    "run_query_market_data",
    "run_web_search",
]
