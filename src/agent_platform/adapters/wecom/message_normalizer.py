"""企业微信消息文本归一化。"""
from __future__ import annotations

import re
from typing import Any, Dict

from agent_platform.adapters.common import NormalizedMessage


_AT_BOT_RE = re.compile(r"@[\w\-]+\s*")


def normalize_wecom_text(frame: Dict[str, Any], *, bot_name: str | None = None) -> NormalizedMessage:
    """从 WeCom frame 抽出文本 + 判定是否 @ 本 bot。

    支持几种常见 payload 形态：
    - 纯文本：``{"text": {"content": "..."}}``
    - 混合：``{"msg_type": "text", "text": {"content": "..."}}``
    - 已归一化的 ``{"content": "..."}``
    """
    text: str = ""
    if isinstance(frame.get("text"), dict):
        text = str(frame["text"].get("content") or "")
    elif isinstance(frame.get("content"), str):
        text = frame["content"]
    elif isinstance(frame.get("msg"), dict):
        text = str(frame["msg"].get("content") or "")
    text = text.strip()

    is_at = False
    if bot_name and f"@{bot_name}" in text:
        is_at = True
        text = text.replace(f"@{bot_name}", "").strip()
    elif _AT_BOT_RE.match(text):
        is_at = True
        text = _AT_BOT_RE.sub("", text, count=1).strip()

    return NormalizedMessage(text=text, is_at_bot=is_at, raw=frame)


__all__ = ["normalize_wecom_text"]
