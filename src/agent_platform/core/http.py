"""HTTP 横切关注点：鉴权、限流。

纯接口声明。monolith 启动时通过 ``register_http_deps()`` 注入实现；
独立 core 包运行时这些函数不可用（返回 401/503）。
"""
from __future__ import annotations

import functools
from typing import Any, Callable, Optional

_require_api_key_impl: Optional[Callable[..., Any]] = None
_require_rate_limit_impl: Optional[Callable[..., Any]] = None


def register_http_deps(
    require_api_key: Callable[..., Any],
    require_rate_limit: Callable[..., Any],
) -> None:
    """由 monolith 启动时调用，注入鉴权/限流实现。"""
    global _require_api_key_impl, _require_rate_limit_impl
    _require_api_key_impl = require_api_key
    _require_rate_limit_impl = require_rate_limit
    # 保留原始签名，FastAPI Depends 需要
    functools.update_wrapper(_require_api_key_proxy, require_api_key)
    functools.update_wrapper(_require_rate_limit_proxy, require_rate_limit)


def _require_api_key_proxy(*args: Any, **kwargs: Any) -> Any:
    if _require_api_key_impl is None:
        raise RuntimeError(
            "require_api_key not registered. "
            "Install agent-platform for full functionality."
        )
    return _require_api_key_impl(*args, **kwargs)


def _require_rate_limit_proxy(*args: Any, **kwargs: Any) -> Any:
    if _require_rate_limit_impl is None:
        raise RuntimeError(
            "require_rate_limit not registered. "
            "Install agent-platform for full functionality."
        )
    return _require_rate_limit_impl(*args, **kwargs)


# 模块级名称，FastAPI Depends 可以引用
require_api_key = _require_api_key_proxy
require_rate_limit = _require_rate_limit_proxy

__all__ = ["require_api_key", "require_rate_limit", "register_http_deps"]
