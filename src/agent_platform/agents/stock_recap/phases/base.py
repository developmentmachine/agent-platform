"""``RecapPhase`` —— 所有 recap Phase 类的公共基类。

提供：
- ``name`` 字段（满足 ``core.orchestration.phase.Phase`` 协议）；
- 统一的 OTEL tracer 注入；
- ``stream`` 默认实现：先发 ``PHASE_START`` → 跑 ``run`` → 发 ``PHASE_END``；
- 调用 ``run`` 时自动用 ``record_phase_duration`` 计时（与历史等价）。
"""
from __future__ import annotations

import time
from typing import Iterator

from agent_platform.agents.stock_recap.state import RecapRunState
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind
from agent_platform.observability.metrics import record_phase_duration
from agent_platform.observability.tracing import get_tracer


class RecapPhase:
    """所有 recap Phase 的最小基类（同 ``core.Phase`` 协议）。"""

    name: str = "base"

    def run(self, state: RecapRunState) -> None:  # pragma: no cover - 由子类覆盖
        raise NotImplementedError

    def stream(self, state: RecapRunState) -> Iterator[StreamEvent]:
        """默认 stream：进 → 执行 → 出。不抛异常的 phase 不需要单独实现 stream。"""
        yield StreamEvent(kind=StreamEventKind.PHASE_START, phase=self.name)
        t0 = time.monotonic()
        try:
            self.run(state)
        except Exception as exc:
            yield StreamEvent(
                kind=StreamEventKind.ERROR,
                phase=self.name,
                data={"message": str(exc)},
            )
            record_phase_duration(f"{self.name}:error", (time.monotonic() - t0) * 1000.0)
            raise
        duration_ms = int((time.monotonic() - t0) * 1000)
        record_phase_duration(self.name, duration_ms)
        yield StreamEvent(
            kind=StreamEventKind.PHASE_END,
            phase=self.name,
            data={"duration_ms": duration_ms},
        )

    @staticmethod
    def _tracer():
        return get_tracer("agent_platform.agents.stock_recap.phases")


__all__ = ["RecapPhase"]
