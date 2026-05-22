"""SessionContext — 会话级上下文（与 PrincipalContext 解耦）。

``conversation_key`` 是「同一对话」的稳定 key（例如 ``wecom:<peer>:<user>``、
``qq:group:<gid>:<uid>``、``cli:<pid>``）；不同入口的归一化由 adapter 完成。

当前 stock-recap 是无状态单 run 模型；``SessionResolverPort`` 的默认实现
（``StatelessSessionResolver``）将 ``session_id`` 与 ``request_id`` 等同，
不影响现有语义。多轮 Agent 后续替换 Resolver 即可。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from agent_platform.core.runtime.principal import PrincipalContext


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    principal: PrincipalContext
    conversation_key: str
    trace_id: str
    started_at_monotonic: float = field(default_factory=time.monotonic)

    @staticmethod
    def new(
        principal: PrincipalContext,
        conversation_key: str,
        *,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> "SessionContext":
        return SessionContext(
            session_id=session_id or uuid.uuid4().hex[:16],
            principal=principal,
            conversation_key=conversation_key,
            trace_id=trace_id or uuid.uuid4().hex,
        )


__all__ = ["SessionContext"]
