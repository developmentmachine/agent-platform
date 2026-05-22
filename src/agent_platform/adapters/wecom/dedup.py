"""基于 msg_id 的进程内去重（LRU）。"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Optional


class MsgIdDedup:
    """LRU 去重：默认保留最近 1024 条消息 ID。"""

    def __init__(self, capacity: int = 1024) -> None:
        self._capacity = max(1, capacity)
        self._seen: "OrderedDict[str, None]" = OrderedDict()
        self._lock = Lock()

    def seen(self, msg_id: Optional[str]) -> bool:
        if not msg_id:
            return False
        with self._lock:
            if msg_id in self._seen:
                self._seen.move_to_end(msg_id)
                return True
            self._seen[msg_id] = None
            if len(self._seen) > self._capacity:
                self._seen.popitem(last=False)
            return False


__all__ = ["MsgIdDedup"]
