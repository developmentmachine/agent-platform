"""默认 SessionResolver — 与现有 stock-recap 单次 run 语义等价。

未来对话型 Agent 替换为 ``RedisSessionResolver`` 等带 TTL 的实现即可。
"""
from __future__ import annotations

from agent_platform.core.ports.session import SessionResolverPort
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.session import SessionContext


class StatelessSessionResolver(SessionResolverPort):
    """每次 resolve 都生成新的 session_id；不持久化。"""

    def resolve(self, principal: PrincipalContext, conversation_key: str) -> SessionContext:
        return SessionContext.new(principal=principal, conversation_key=conversation_key)


__all__ = ["StatelessSessionResolver"]
