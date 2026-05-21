"""Phase 协议 — 单个编排阶段的最小抽象。

新 Agent 把每个阶段实现为一个 Phase 子类；stock-recap 当前的
``_phase_*`` 函数将在后续 commit 类化为 ``PerceivePhase`` / ``RecallPhase``
等，并直接复用平台的 budget / tracing 装饰逻辑。
"""
from __future__ import annotations

from typing import Generic, Iterator, Protocol, TypeVar, runtime_checkable

from agent_platform.core.orchestration.stream_events import StreamEvent

StateT = TypeVar("StateT")


@runtime_checkable
class Phase(Protocol, Generic[StateT]):
    """单个 phase 必须暴露的最小契约。"""

    name: str

    def run(self, state: StateT) -> None:
        """同步执行；可改写 ``state`` 累计上下文。失败请抛异常，平台层统一处理。"""
        ...

    def stream(self, state: StateT) -> Iterator[StreamEvent]:
        """流式执行；默认实现可在子类中复用 ``run`` + ``yield`` 两个 phase_start/end。"""
        ...


__all__ = ["Phase", "StateT"]
