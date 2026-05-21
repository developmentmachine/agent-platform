"""所有 adapter 共享的类型与归一化工具。

设计目标：每个 connector（CLI / HTTP / WeCom / QQ）只做四件事：
1. ``MessageNormalizer``    解析平台原始 frame → 文本 + 是否 @bot
2. ``FrameMapper``          原始 frame → ``PrincipalContext`` + ``conversation_key``
3. ``Dedup``                按 msg_id / msg_seq 去重
4. ``runtime.run({...})``   投递给 AgentRuntime
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent_platform.core.runtime.principal import PrincipalContext


@dataclass
class NormalizedMessage:
    """从任意平台抽取出的最小消息模型。"""

    text: str
    is_at_bot: bool = False
    raw: Dict[str, Any] | None = None


@dataclass
class AdapterContext:
    """单条入站消息的归一化上下文 — 准备喂给 ``AgentRuntime.run`` 的全部信息。"""

    principal: PrincipalContext
    conversation_key: str
    message: NormalizedMessage
    agent_id: str
    trace_id: Optional[str] = None
    extras: Dict[str, Any] | None = None


def build_conversation_key(*parts: str) -> str:
    """统一拼装 conversation_key：用冒号分隔，避免与 raw id 中的 ``-`` 等冲突。

    示例：
    - ``build_conversation_key("wecom", peer_id, user_id)``
    - ``build_conversation_key("qq", "group", group_id, user_id)``
    - ``build_conversation_key("qq", "c2c", user_id)``
    """
    return ":".join(p for p in parts if p)


__all__ = [
    "AdapterContext",
    "NormalizedMessage",
    "build_conversation_key",
]
