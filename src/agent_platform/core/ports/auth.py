"""鉴权 Port：定义 HTTP 请求的身份验证和限流接口。

agents 依赖此 Port，adapters 提供具体实现（FastAPI Depends）。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    """请求级身份验证提供者。"""

    def require_api_key(self, *args, **kwargs) -> object:
        """验证 API Key 并返回 PrincipalContext。"""
        ...

    def require_rate_limit(self, *args, **kwargs) -> None:
        """检查速率限制。"""
        ...
