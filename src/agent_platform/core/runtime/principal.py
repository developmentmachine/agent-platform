"""PrincipalContext — 跨入口的统一身份上下文。

设计要点：
- ``subject`` 是稳定标识（CLI 用户名 / OpenID / api key fingerprint）；
- ``source`` 表达「从哪条接入进来」，与 audit / trace 直接挂钩；
- ``role`` 用于 ``ToolPolicy.required_role`` 与未来 RBAC 拦截；
- 向下兼容：现有 ``agent_platform.domain.principal`` 模块继续工作，本 dataclass
  是它的 Pydantic-风格升级版本，**先并存**。
"""
from __future__ import annotations

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
]


@dataclass(frozen=True)
class PrincipalContext:
    """请求级身份上下文（不可变）。"""

    subject: str
    source: PrincipalSource
    tenant_id: Optional[str] = None
    role: str = "user"
    display_name: Optional[str] = None

    @classmethod
    def anonymous(cls, source: PrincipalSource = "cli") -> "PrincipalContext":
        return cls(subject="anonymous", source=source, role="user")


__all__ = ["PrincipalContext", "PrincipalSource"]
