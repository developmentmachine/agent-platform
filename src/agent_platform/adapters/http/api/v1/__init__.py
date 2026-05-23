"""``/v1/`` API 子路由集合。

每个 feature 一个 ``APIRouter``，通过 ``ops.register`` / ``recap.register`` ...
在 app factory 中装配。便于后续按版本路由（v2）或按租户 tenant 路由拆分。
"""
from agent_platform.agents.stock_recap.http_routes import feedback_router, recap_router
from agent_platform.adapters.http.api.v1.jobs import router as jobs_router
from agent_platform.adapters.http.api.v1.ops import router as ops_router

__all__ = ["ops_router", "recap_router", "feedback_router", "jobs_router"]
