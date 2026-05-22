"""QQ Bot WebSocket Identify token 构造。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

QqWsAuthMode = Literal["bot_token", "app_token"]


@dataclass(frozen=True)
class QqWsIdentify:
    token: str
    intents: int
    shard: tuple[int, int] = (0, 1)


def build_ws_identify_token(
    *,
    app_id: str,
    app_secret: str,
    mode: QqWsAuthMode = "app_token",
) -> str:
    """构造 Identify 帧的 token 字段。

    占位实现：实际 token 协商在 connector 真实接入时实现（含 OAuth2 / refresh）；
    本文件仅约定 API surface。
    """
    if mode == "bot_token":
        return f"Bot {app_id}.{app_secret}"
    return f"QQBot {app_id}.{app_secret}"


def parse_qq_ws_auth_mode(value: str | None) -> QqWsAuthMode:
    if not value:
        return "app_token"
    v = value.strip().lower()
    if v in ("bot", "bot_token"):
        return "bot_token"
    return "app_token"


__all__ = ["QqWsAuthMode", "QqWsIdentify", "build_ws_identify_token", "parse_qq_ws_auth_mode"]
