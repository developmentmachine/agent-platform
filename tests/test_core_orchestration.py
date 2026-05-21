"""Phase / Pipeline / SideEffectBus 的最小行为测试（与 recap 解耦）。"""
from __future__ import annotations

import time
from dataclasses import dataclass

from agent_platform.core.orchestration import (
    Phase,
    Pipeline,
    PipelineConfig,
    SideEffectBus,
    SideEffectContext,
    StandardEvent,
    StreamEvent,
    StreamEventKind,
)
from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext


@dataclass
class _State(RunState):
    counter: int = 0


class _Incr(Phase[_State]):
    name = "incr"

    def __init__(self, by: int = 1) -> None:
        self._by = by

    def run(self, state: _State) -> None:
        state.counter += self._by

    def stream(self, state: _State):
        self.run(state)
        yield StreamEvent(kind=StreamEventKind.PHASE_PROGRESS, phase=self.name, data={"counter": state.counter})


def _make_state() -> _State:
    return _State(
        run_ctx=RunContext.new(),
        principal=PrincipalContext.anonymous(),
        started_at_monotonic=time.monotonic(),
        counter=0,
    )


def test_pipeline_executes_phases_in_order():
    pipeline = Pipeline([_Incr(1), _Incr(2), _Incr(3)])
    state = _make_state()
    pipeline.execute(state)
    assert state.counter == 6


def test_pipeline_stream_yields_phase_events():
    pipeline = Pipeline([_Incr(1), _Incr(2)])
    state = _make_state()
    events = list(pipeline.stream(state))
    kinds = [e.kind for e in events]
    assert kinds[0] == StreamEventKind.PHASE_START
    assert StreamEventKind.PHASE_END in kinds
    assert kinds[-1] == StreamEventKind.COMPLETED
    assert state.counter == 3


def test_side_effect_bus_emits_completed():
    bus = SideEffectBus()
    received: list[str] = []
    bus.subscribe(StandardEvent.RUN_COMPLETED, lambda ctx: received.append("done"))
    pipeline = Pipeline([_Incr()], side_effects=bus)
    pipeline.execute(_make_state())
    assert received == ["done"]


def test_side_effect_bus_handles_failure_event():
    class _Boom(Phase[_State]):
        name = "boom"

        def run(self, state: _State) -> None:
            raise RuntimeError("kaboom")

        def stream(self, state: _State):
            self.run(state)
            if False:
                yield  # pragma: no cover

    bus = SideEffectBus()
    failures: list[str] = []
    bus.subscribe(StandardEvent.RUN_FAILED, lambda ctx: failures.append(ctx.payload.get("phase", "?")))
    pipeline = Pipeline([_Boom()], side_effects=bus)
    state = _make_state()
    try:
        pipeline.execute(state)
    except RuntimeError:
        pass
    assert failures == ["boom"]


def test_side_effect_handler_errors_are_swallowed_by_default():
    bus = SideEffectBus()
    def _bad(ctx: SideEffectContext) -> None:
        raise ValueError("ignored")
    bus.subscribe(StandardEvent.RUN_COMPLETED, _bad)
    pipeline = Pipeline([_Incr()], side_effects=bus, config=PipelineConfig(check_budget_between_phases=False))
    pipeline.execute(_make_state())
