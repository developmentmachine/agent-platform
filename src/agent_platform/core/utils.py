"""共享工具函数：供 core / agents / adapters 共用，无上层依赖。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str() -> str:
    """当前本地日期的 YYYY-MM-DD 字符串。"""
    return datetime.now().strftime("%Y-%m-%d")


def stable_json(obj: Any) -> str:
    """稳定的 JSON 序列化（ensure_ascii=False, sort_keys=True）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["stable_json", "today_str", "utc_now_iso"]
