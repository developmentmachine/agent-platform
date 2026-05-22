"""QQ frame → AdapterContext 的归一化（群消息 + C2C 私聊）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agent_platform.adapters.common import build_conversation_key
from agent_platform.core.runtime.principal import PrincipalContext


def map_qq_group_message(
    frame: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
) -> tuple[PrincipalContext, str]:
    group_id = str(frame.get("group_openid") or frame.get("group_id") or "unknown")
    user_id = str(
        (frame.get("author") or {}).get("member_openid")
        or frame.get("user_openid")
        or frame.get("user_id")
        or "unknown"
    )
    principal = PrincipalContext(
        subject=user_id,
        source="qq_group",
        tenant_id=tenant_id,
        role="user",
    )
    return principal, build_conversation_key("qq", "group", group_id, user_id)


def map_qq_c2c_message(
    frame: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
) -> tuple[PrincipalContext, str]:
    user_id = str(
        (frame.get("author") or {}).get("user_openid")
        or frame.get("user_id")
        or "unknown"
    )
    principal = PrincipalContext(
        subject=user_id,
        source="qq_c2c",
        tenant_id=tenant_id,
        role="user",
    )
    return principal, build_conversation_key("qq", "c2c", user_id)


__all__ = ["map_qq_group_message", "map_qq_c2c_message"]
