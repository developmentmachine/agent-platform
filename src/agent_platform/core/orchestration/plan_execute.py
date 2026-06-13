"""PlanExecutePipeline — Plan → Execute Subgoals → Replan 编排原语。

Plan-and-Execute 认知架构：
1. Planner: LLM 将任务分解为子目标列表
2. Executor: 顺序执行每个子目标（可调用工具）
3. Replanner: 执行完每个子目标后，LLM 可修订剩余计划
4. Final: 聚合所有子目标结果产出最终答案

使用方式：
    state = PlanExecuteState(
        run_ctx=ctx, principal=principal,
        task="分析今日A股并给出投资建议",
        planner_fn=my_planner,
        executor_fn=my_executor,
        replanner_fn=my_replanner,  # 可选
    )
    pipeline = PlanExecutePipeline(max_replans=2)
    pipeline.execute(state)
    print(state.final_answer)

所有 LLM/工具调用通过 state 上的注入函数完成（DI 模式），
不依赖任何 infra 实现。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional

from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.side_effects_bus import (
    SideEffectBus,
    SideEffectContext,
    StandardEvent,
)
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind

logger = logging.getLogger("agent_platform.core.orchestration.plan_execute")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Planner: (task, context) -> list of subgoal descriptions
PlannerFn = Callable[[str, Dict[str, Any]], List[str]]

# Executor: (subgoal_description, context) -> result_text
ExecutorFn = Callable[[str, Dict[str, Any]], str]

# Replanner: (task, completed_goals, remaining_goals, context) -> revised_remaining_goals
ReplannerFn = Callable[[str, List["Subgoal"], List["Subgoal"], Dict[str, Any]], List[str]]


class SubgoalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Subgoal:
    """单个子目标。"""
    id: int
    description: str
    status: SubgoalStatus = SubgoalStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PlanExecuteState(RunState):
    """Plan-and-Execute 的状态。

    Agent 在创建时注入：
    - task: 任务描述
    - planner_fn: 生成子目标列表
    - executor_fn: 执行单个子目标
    - replanner_fn: 修订剩余计划（可选）
    """
    task: str = ""
    planner_fn: Optional[PlannerFn] = None
    executor_fn: Optional[ExecutorFn] = None
    replanner_fn: Optional[ReplannerFn] = None
    # 上下文（传递给 planner/executor/replanner）
    context: Dict[str, Any] = field(default_factory=dict)
    # 结果
    subgoals: List[Subgoal] = field(default_factory=list)
    final_answer: Optional[str] = None


# ---------------------------------------------------------------------------
# PlanExecutePipeline
# ---------------------------------------------------------------------------

class PlanExecutePipeline:
    """Plan → Execute Subgoals → Replan 循环。

    与 Pipeline 接口对齐：提供 execute(state) 和 stream(state)。
    """

    def __init__(
        self,
        max_replans: int = 3,
        *,
        side_effects: Optional[SideEffectBus] = None,
    ) -> None:
        self._max_replans = max_replans
        self._bus = side_effects

    # ── 同步执行 ──────────────────────────────────────────────────────

    def execute(self, state: PlanExecuteState) -> None:
        """同步执行 Plan-and-Execute 流程。"""
        self._validate(state)

        # Phase 1: Plan
        self._plan(state)
        if not state.subgoals:
            state.final_answer = "No subgoals generated"
            self._emit_completed(state)
            return

        # Phase 2: Execute with optional replanning
        replans = 0
        while state.subgoals:
            # Find next pending subgoal
            next_goal = self._next_pending(state)
            if next_goal is None:
                break

            # Execute
            self._execute_subgoal(state, next_goal)

            # Replan (if replanner provided and not the last goal)
            has_remaining = any(g.status == SubgoalStatus.PENDING for g in state.subgoals)
            if has_remaining and state.replanner_fn and replans < self._max_replans:
                changed = self._replan(state)
                if changed:
                    replans += 1

        # Phase 3: Aggregate
        self._aggregate(state)
        self._emit_completed(state)

    # ── 流式执行 ──────────────────────────────────────────────────────

    def stream(self, state: PlanExecuteState) -> Iterator[StreamEvent]:
        """流式执行 Plan-and-Execute，产出 StreamEvent。"""
        self._validate(state)

        yield StreamEvent(kind=StreamEventKind.PHASE_START, phase="plan", data={"task": state.task})

        # Plan
        self._plan(state)
        yield StreamEvent(
            kind=StreamEventKind.PLAN_GENERATED,
            data={"subgoals": [{"id": g.id, "description": g.description} for g in state.subgoals]},
        )
        yield StreamEvent(kind=StreamEventKind.PHASE_END, phase="plan")

        if not state.subgoals:
            state.final_answer = "No subgoals generated"
            yield StreamEvent(kind=StreamEventKind.COMPLETED)
            self._emit_completed(state)
            return

        # Execute with replanning
        replans = 0
        while state.subgoals:
            next_goal = self._next_pending(state)
            if next_goal is None:
                break

            yield StreamEvent(
                kind=StreamEventKind.SUBGOAL_START,
                phase="execute",
                data={"id": next_goal.id, "description": next_goal.description},
            )

            self._execute_subgoal(state, next_goal)

            yield StreamEvent(
                kind=StreamEventKind.SUBGOAL_DONE,
                phase="execute",
                data={"id": next_goal.id, "result": next_goal.result, "status": next_goal.status.value},
            )

            # Replan
            has_remaining = any(g.status == SubgoalStatus.PENDING for g in state.subgoals)
            if has_remaining and state.replanner_fn and replans < self._max_replans:
                old_count = len([g for g in state.subgoals if g.status == SubgoalStatus.PENDING])
                changed = self._replan(state)
                if changed:
                    replans += 1
                    new_count = len([g for g in state.subgoals if g.status == SubgoalStatus.PENDING])
                    yield StreamEvent(
                        kind=StreamEventKind.REPLAN,
                        data={"old_remaining": old_count, "new_remaining": new_count, "replans_used": replans},
                    )

        # Aggregate
        self._aggregate(state)
        yield StreamEvent(kind=StreamEventKind.AGENT_OUTPUT, data={"answer": state.final_answer})
        yield StreamEvent(kind=StreamEventKind.COMPLETED)
        self._emit_completed(state)

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _validate(self, state: PlanExecuteState) -> None:
        if not state.planner_fn:
            raise ValueError("PlanExecuteState.planner_fn is required")
        if not state.executor_fn:
            raise ValueError("PlanExecuteState.executor_fn is required")
        if not state.task:
            raise ValueError("PlanExecuteState.task is required")

    def _plan(self, state: PlanExecuteState) -> None:
        t0 = time.monotonic()
        descriptions = state.planner_fn(state.task, state.context)  # type: ignore[misc]
        state.subgoals = [
            Subgoal(id=i + 1, description=desc)
            for i, desc in enumerate(descriptions)
        ]
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("plan generated %d subgoals in %dms", len(state.subgoals), duration_ms)

    def _next_pending(self, state: PlanExecuteState) -> Optional[Subgoal]:
        for g in state.subgoals:
            if g.status == SubgoalStatus.PENDING:
                return g
        return None

    def _execute_subgoal(self, state: PlanExecuteState, goal: Subgoal) -> None:
        goal.status = SubgoalStatus.RUNNING
        t0 = time.monotonic()
        try:
            goal.result = state.executor_fn(goal.description, state.context)  # type: ignore[misc]
            goal.status = SubgoalStatus.DONE
        except Exception as e:
            goal.error = str(e)
            goal.status = SubgoalStatus.FAILED
            logger.warning("subgoal %d failed: %s", goal.id, e)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("subgoal %d completed in %dms status=%s", goal.id, duration_ms, goal.status.value)

    def _replan(self, state: PlanExecuteState) -> bool:
        """修订剩余计划。返回 True 表示计划有变化。"""
        completed = [g for g in state.subgoals if g.status in (SubgoalStatus.DONE, SubgoalStatus.FAILED)]
        remaining = [g for g in state.subgoals if g.status == SubgoalStatus.PENDING]
        if not remaining:
            return False

        old_descriptions = [g.description for g in remaining]
        new_descriptions = state.replanner_fn(  # type: ignore[misc]
            state.task, completed, remaining, state.context,
        )

        if new_descriptions == old_descriptions:
            return False

        # Replace remaining subgoals
        max_id = max(g.id for g in state.subgoals)
        new_goals = [
            Subgoal(id=max_id + i + 1, description=desc)
            for i, desc in enumerate(new_descriptions)
        ]
        # Remove old pending, add new
        state.subgoals = [g for g in state.subgoals if g.status != SubgoalStatus.PENDING] + new_goals
        logger.debug("replan: %d remaining -> %d new goals", len(remaining), len(new_goals))
        return True

    def _aggregate(self, state: PlanExecuteState) -> None:
        """聚合所有子目标结果为最终答案。"""
        done_goals = [g for g in state.subgoals if g.status == SubgoalStatus.DONE]
        if not done_goals:
            state.final_answer = "All subgoals failed"
            return

        parts = []
        for g in done_goals:
            parts.append(f"[Subgoal {g.id}] {g.description}\n{g.result}")
        state.final_answer = "\n\n".join(parts)

    def _emit_completed(self, state: PlanExecuteState) -> None:
        if self._bus is not None:
            self._bus.emit(
                StandardEvent.RUN_COMPLETED,
                SideEffectContext(
                    run_ctx=state.run_ctx,
                    principal=state.principal,
                    payload={"subgoals": len(state.subgoals)},
                ),
            )


__all__ = [
    "PlanExecutePipeline",
    "PlanExecuteState",
    "Subgoal",
    "SubgoalStatus",
    "PlannerFn",
    "ExecutorFn",
    "ReplannerFn",
]
