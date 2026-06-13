"""向后兼容 shim — jobs 路由已迁入 agents.stock_recap.http_routes.jobs。

.. deprecated::
    本路由已由 stock_recap agent 通过 manifest http_router_factories 注册。
    本文件将在下个大版本移除。
"""
from __future__ import annotations

import warnings

warnings.warn(
    "agent_platform.adapters.http.v1.jobs is deprecated; "
    "routes are now registered by the stock_recap agent via manifest.",
    DeprecationWarning,
    stacklevel=2,
)

from agent_platform.agents.stock_recap.http_routes.jobs import router  # noqa: F401

__all__ = ["router"]
