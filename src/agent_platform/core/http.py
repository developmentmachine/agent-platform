"""HTTP 横切关注点：鉴权、限流。

这些是 FastAPI Depends 函数，供 agents 的 HTTP 路由使用。
实现层在 adapters/http/deps.py，此处用惰性导入避免 core → adapters 依赖。
"""
from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "require_api_key":
        from agent_platform.adapters.http.deps import require_api_key
        return require_api_key
    if name == "require_rate_limit":
        from agent_platform.adapters.http.deps import require_rate_limit
        return require_rate_limit
    raise AttributeError(name)


__all__ = ["require_api_key", "require_rate_limit"]
