"""会话解析 Port — 把 (principal, conversation_key) 解析为 SessionContext。

默认实现为 1:1 映射 (StatelessSessionResolver)，与现有 stock-recap 单次 run 语义
等价；未来对话型 Agent 替换此实现即可。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.session import SessionContext


@runtime_checkable
class SessionResolverPort(Protocol):
    def resolve(self, principal: PrincipalContext, conversation_key: str) -> SessionContext:
        ...
