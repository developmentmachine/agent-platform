"""推送 Port：企业微信 / Lark / Slack / Email 等外部通道的最小抽象。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class PushResult:
    ok: bool
    channel: str
    detail: Optional[str] = None
    meta: Dict[str, Any] = None  # type: ignore[assignment]


@runtime_checkable
class PushPort(Protocol):
    """同步推送一段已渲染好的内容到外部通道。"""

    channel: str

    def push(
        self,
        rendered: str,
        *,
        title: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> PushResult:
        ...
