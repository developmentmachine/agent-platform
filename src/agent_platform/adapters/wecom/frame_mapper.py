"""企业微信 frame → AdapterContext 的归一化。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agent_platform.adapters.common import build_conversation_key
from agent_platform.core.runtime.principal import PrincipalContext


def _peer_id(frame: Dict[str, Any]) -> str:
    """优先群 ID，否则单聊用 user_id 作 peer。"""
    return (
        frame.get("chat_id")
        or frame.get("group_id")
        or frame.get("from_user_id")
        or frame.get("from", {}).get("userid")
        or "unknown"
    )


def _user_id(frame: Dict[str, Any]) -> str:
    return (
        frame.get("from_user_id")
        or frame.get("from", {}).get("userid")
        or frame.get("user_id")
        or "unknown"
    )


def map_wecom_frame(
    frame: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
) -> tuple[PrincipalContext, str]:
    """返回 ``(principal, conversation_key)``。"""
    user = _user_id(frame)
    peer = _peer_id(frame)
    principal = PrincipalContext(
        subject=user,
        source="wecom",
        tenant_id=tenant_id,
        role="user",
        display_name=frame.get("from", {}).get("name") if isinstance(frame.get("from"), dict) else None,
    )
    return principal, build_conversation_key("wecom", peer, user)


__all__ = ["map_wecom_frame"]
