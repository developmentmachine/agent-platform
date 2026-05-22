"""WeCom 流式回复辅助 — 把 AgentRuntime.stream 的 NDJSON 事件转成文本增量。

后续 commit 接入企微 AiBot SDK 时，``flush(text)`` 替换为真正的回复 API。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable


@dataclass
class StreamReplyBuffer:
    """把 NDJSON 流缓冲为可读文本，按阶段产出进度。"""

    on_flush: Callable[[str], None]
    progress_prefix: str = "·"

    def consume(self, events: Iterable[Dict[str, Any]]) -> None:
        for ev in events:
            self._handle(ev)

    def _handle(self, ev: Dict[str, Any]) -> None:
        kind = ev.get("kind") or ev.get("event") or ""
        if kind == "phase_start":
            self.on_flush(f"{self.progress_prefix} {ev.get('phase')}…")
        elif kind == "agent_output":
            txt = (ev.get("data") or {}).get("text") or ev.get("text")
            if txt:
                self.on_flush(str(txt))
        elif kind == "completed":
            self.on_flush("✓ 完成")
        elif kind == "error":
            self.on_flush(f"⚠ {((ev.get('data') or {}).get('message')) or '错误'}")


__all__ = ["StreamReplyBuffer"]
