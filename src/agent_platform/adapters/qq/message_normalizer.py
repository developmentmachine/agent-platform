"""QQ 消息文本归一化（与 wecom 同接口形态）。"""
from __future__ import annotations

import re
from typing import Any, Dict

from agent_platform.adapters.common import NormalizedMessage


_AT_BOT_RE = re.compile(r"<@!?\d+>\s*")


def normalize_qq_text(frame: Dict[str, Any], *, bot_user_id: str | None = None) -> NormalizedMessage:
    text = str(frame.get("content") or frame.get("text") or "").strip()
    is_at = False
    if bot_user_id and f"<@{bot_user_id}>" in text:
        is_at = True
        text = text.replace(f"<@{bot_user_id}>", "").strip()
    elif _AT_BOT_RE.match(text):
        is_at = True
        text = _AT_BOT_RE.sub("", text, count=1).strip()
    return NormalizedMessage(text=text, is_at_bot=is_at, raw=frame)


__all__ = ["normalize_qq_text"]
