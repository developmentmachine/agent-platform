"""PrincipalContext — 跨入口的统一身份上下文（多租户 / RBAC / 会话主体）。

字段语义：
- ``subject``：稳定调用者标识（OpenID / 租户 ID / CLI 用户等）；
- ``source``：接入通道（与 audit / trace 挂钩）；
- ``tenant_id`` / ``role`` / ``api_key_hash``：多租户与 RBAC；
- ``client_host``：HTTP 等场景下的客户端地址（勿与 ``source`` 通道混用）；
- ``display_name``：展示名（企微 / QQ 等可选）。

请求级 ContextVar：
- ``set_principal(p)`` 在 FastAPI 依赖或 job worker 入口调用；
- ``get_principal()`` 供工具治理 / 持久化 / 副作用推断 tenant；
- 线程池任务不自动继承，必要时 ``copy_context().run(fn)``。
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Literal, Optional

PrincipalSource = Literal[
    "cli",
    "http",
    "wecom",
    "qq_group",
    "qq_c2c",
    "scheduler",
    "mcp",
    "test",
    "job-worker",
]


@dataclass(frozen=True)
class PrincipalContext:
    """请求级身份上下文（不可变）。"""

    subject: str = "anonymous"
    source: PrincipalSource = "cli"
    tenant_id: Optional[str] = None
    role: str = "user"
    api_key_hash: Optional[str] = None
    display_name: Optional[str] = None
    client_host: Optional[str] = None

    @staticmethod
    def system() -> "PrincipalContext":
        """系统级身份：outbox sweep / 内部任务，RBAC 视为 admin。"""
        return PrincipalContext(
            subject="system",
            source="scheduler",
            tenant_id=None,
            role="admin",
            api_key_hash="system",
        )

    @classmethod
    def anonymous(cls, source: PrincipalSource = "cli") -> "PrincipalContext":
        return cls(subject="anonymous", source=source, role="user")


current_principal: contextvars.ContextVar[PrincipalContext] = contextvars.ContextVar(
    "current_principal",
    default=PrincipalContext.anonymous(),
)


def set_principal(principal: PrincipalContext) -> object:
    """返回 token，调用方可在 finally 里 ``current_principal.reset(token)``。"""
    return current_principal.set(principal)


def get_principal() -> PrincipalContext:
    return current_principal.get()


__all__ = [
    "PrincipalContext",
    "PrincipalSource",
    "current_principal",
    "get_principal",
    "set_principal",
]
