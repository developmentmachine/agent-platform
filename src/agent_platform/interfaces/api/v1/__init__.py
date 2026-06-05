"""shim → agent_platform.adapters.http.v1"""
from agent_platform.adapters.http.v1 import (  # noqa: F401
    jobs_router,
    ops_router,
)

__all__ = ["jobs_router", "ops_router"]
