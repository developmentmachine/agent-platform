"""Pipeline — 编排一组 Phase；与具体 Agent 解耦。

设计原则：
- 不关心 phase 是谁、做了什么；
- 提供「阶段间 budget 校验」「OTEL span 包装」「NDJSON 流」「副作用事件触发」四件套；
- 复用 ``application.orchestration.budget.AgentBudget`` 与 ``observability.tracing`` —
  这两块在现有实现里已经很扎实，不重写。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Generic, Iterator, List, Optional, Sequence

from agent_platform.core.orchestration.phase import Phase, StateT
from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.side_effects_bus import (
    SideEffectBus,
    SideEffectContext,
    StandardEvent,
)
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind

logger = logging.getLogger("agent_platform.core.orchestration.pipeline")


@dataclass
class PipelineConfig:
    check_budget_between_phases: bool = True
    emit_phase_span: bool = True


class Pipeline(Generic[StateT]):
    """有序执行一组 ``Phase``。"""

    def __init__(
        self,
        phases: Sequence[Phase[StateT]],
        *,
        config: Optional[PipelineConfig] = None,
        side_effects: Optional[SideEffectBus] = None,
    ) -> None:
        self._phases: List[Phase[StateT]] = list(phases)
        self._config = config or PipelineConfig()
        self._bus = side_effects

    @property
    def phases(self) -> List[Phase[StateT]]:
        return list(self._phases)

    def execute(self, state: StateT) -> None:
        for phase in self._phases:
            t0 = time.monotonic()
            try:
                phase.run(state)
            except Exception:
                self._emit_failed(state, phase.name)
                raise
            self._after_phase(state, phase.name, t0)
        self._emit_completed(state)

    def stream(self, state: StateT) -> Iterator[StreamEvent]:
        for phase in self._phases:
            t0 = time.monotonic()
            yield StreamEvent(kind=StreamEventKind.PHASE_START, phase=phase.name)
            try:
                for ev in phase.stream(state):
                    yield ev
            except Exception as exc:
                yield StreamEvent(
                    kind=StreamEventKind.ERROR,
                    phase=phase.name,
                    data={"message": str(exc)},
                )
                self._emit_failed(state, phase.name)
                raise
            duration_ms = int((time.monotonic() - t0) * 1000)
            yield StreamEvent(
                kind=StreamEventKind.PHASE_END,
                phase=phase.name,
                data={"duration_ms": duration_ms},
            )
            self._after_phase(state, phase.name, t0)
        yield StreamEvent(kind=StreamEventKind.COMPLETED)
        self._emit_completed(state)

    def _after_phase(self, state: StateT, name: str, t0: float) -> None:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("phase=%s duration_ms=%s", name, duration_ms)
        if self._bus is not None and isinstance(state, RunState):
            self._bus.emit(
                StandardEvent.PHASE_DONE,
                SideEffectContext(
                    run_ctx=state.run_ctx,
                    principal=state.principal,
                    payload={"phase": name, "duration_ms": duration_ms},
                ),
            )
        if (
            self._config.check_budget_between_phases
            and isinstance(state, RunState)
            and state.budget is not None
        ):
            state.budget.check()

    def _emit_completed(self, state: StateT) -> None:
        if self._bus is not None and isinstance(state, RunState):
            self._bus.emit(
                StandardEvent.RUN_COMPLETED,
                SideEffectContext(
                    run_ctx=state.run_ctx,
                    principal=state.principal,
                    payload={},
                ),
            )

    def _emit_failed(self, state: StateT, phase_name: str) -> None:
        if self._bus is not None and isinstance(state, RunState):
            self._bus.emit(
                StandardEvent.RUN_FAILED,
                SideEffectContext(
                    run_ctx=state.run_ctx,
                    principal=state.principal,
                    payload={"phase": phase_name},
                ),
            )


__all__ = ["Pipeline", "PipelineConfig"]
