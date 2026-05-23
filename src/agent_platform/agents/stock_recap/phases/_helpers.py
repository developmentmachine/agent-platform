"""Phase 实现共享工具（W4 去 legacy）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def span_phase(tracer: Any, name: str, attrs: Optional[dict[str, Any]] = None) -> Any:
    return tracer.start_as_current_span(name, attributes=attrs or {})


__all__ = ["utc_now_iso", "span_phase", "stable_json"]
