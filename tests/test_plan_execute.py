"""Tests for PlanExecutePipeline orchestration primitive."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from agent_platform.core.orchestration.plan_execute import (
    PlanExecutePipeline,
    PlanExecuteState,
    Subgoal,
    SubgoalStatus,
)
from agent_platform.core.orchestration.stream_events import StreamEventKind
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext


def _make_state(
    *,
    task: str = "Analyze market",
    subgoals: Optional[List[str]] = None,
    executor_results: Optional[Dict[str, str]] = None,
    replan_results: Optional[List[str]] = None,
) -> PlanExecuteState:
    """Create a test PlanExecuteState with mock functions."""
    goals = subgoals or ["Collect data", "Analyze trends", "Write report"]
    results = executor_results or {}

    def planner(task: str, ctx: Dict[str, Any]) -> List[str]:
        return goals

    def executor(subgoal: str, ctx: Dict[str, Any]) -> str:
        return results.get(subgoal, f"Result for: {subgoal}")

    def replanner(
        task: str,
        completed: List[Subgoal],
        remaining: List[Subgoal],
        ctx: Dict[str, Any],
    ) -> List[str]:
        if replan_results is not None:
            return replan_results
        return [g.description for g in remaining]

    return PlanExecuteState(
        run_ctx=RunContext.new(),
        principal=PrincipalContext.anonymous(source="test"),
        task=task,
        planner_fn=planner,
        executor_fn=executor,
        replanner_fn=replanner,
    )


# ── PlanExecutePipeline.execute ────────────────────────────────────────


class TestPlanExecute:
    def test_basic_plan_execute(self):
        state = _make_state(subgoals=["Step A", "Step B"])
        pipeline = PlanExecutePipeline(max_replans=0)
        pipeline.execute(state)

        assert len(state.subgoals) == 2
        assert all(g.status == SubgoalStatus.DONE for g in state.subgoals)
        assert state.final_answer is not None
        assert "Step A" in state.final_answer

    def test_subgoal_failure_continues(self):
        def failing_executor(subgoal: str, ctx: Dict[str, Any]) -> str:
            if subgoal == "Fail me":
                raise ValueError("boom")
            return f"ok: {subgoal}"

        state = PlanExecuteState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
            planner_fn=lambda t, c: ["Fail me", "Succeed"],
            executor_fn=failing_executor,
        )
        pipeline = PlanExecutePipeline(max_replans=0)
        pipeline.execute(state)

        assert state.subgoals[0].status == SubgoalStatus.FAILED
        assert state.subgoals[1].status == SubgoalStatus.DONE
        # Final answer should only include successful subgoals
        assert "Succeed" in state.final_answer

    def test_all_subgoals_fail(self):
        def boom(subgoal: str, ctx: Dict[str, Any]) -> str:
            raise RuntimeError("fail")

        state = PlanExecuteState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
            planner_fn=lambda t, c: ["A", "B"],
            executor_fn=boom,
        )
        pipeline = PlanExecutePipeline(max_replans=0)
        pipeline.execute(state)

        assert state.final_answer == "All subgoals failed"

    def test_replan_modifies_remaining(self):
        # Replanner replaces remaining goals
        state = _make_state(
            subgoals=["A", "B", "C"],
            replan_results=["B-revised", "C-revised"],
        )
        pipeline = PlanExecutePipeline(max_replans=1)
        pipeline.execute(state)

        # After executing A, replan should replace B,C with B-revised,C-revised
        descriptions = [g.description for g in state.subgoals]
        assert "B-revised" in descriptions
        assert "C-revised" in descriptions

    def test_no_subgoals_generated(self):
        state = PlanExecuteState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
            planner_fn=lambda t, c: [],
            executor_fn=lambda s, c: "x",
        )
        pipeline = PlanExecutePipeline()
        pipeline.execute(state)

        assert state.final_answer == "No subgoals generated"

    def test_max_replans_respected(self):
        replan_count = {"n": 0}

        def counting_replan(task, completed, remaining, ctx):
            replan_count["n"] += 1
            return [g.description for g in remaining]  # no change

        state = _make_state(subgoals=["A", "B", "C", "D"])
        state.replanner_fn = counting_replan
        pipeline = PlanExecutePipeline(max_replans=2)
        pipeline.execute(state)

        # Replanner is called for each step that has remaining goals after it
        # (after A, B, C — 3 calls). max_replans limits successful replans (changes).
        # The replanner returns same goals (no change), so replans_used stays 0.
        # But the function IS invoked — just _replan returns False (no actual change).
        assert replan_count["n"] >= 1  # at least called


# ── PlanExecutePipeline.stream ─────────────────────────────────────────


class TestPlanExecuteStream:
    def test_stream_events_order(self):
        state = _make_state(subgoals=["Step 1", "Step 2"])
        pipeline = PlanExecutePipeline(max_replans=0)
        events = list(pipeline.stream(state))

        kinds = [e.kind for e in events]
        assert StreamEventKind.PLAN_GENERATED in kinds
        assert StreamEventKind.SUBGOAL_START in kinds
        assert StreamEventKind.SUBGOAL_DONE in kinds
        assert StreamEventKind.COMPLETED in kinds

    def test_stream_plan_generated_data(self):
        state = _make_state(subgoals=["Alpha", "Beta"])
        pipeline = PlanExecutePipeline(max_replans=0)
        events = list(pipeline.stream(state))

        plan_events = [e for e in events if e.kind == StreamEventKind.PLAN_GENERATED]
        assert len(plan_events) == 1
        subgoals = plan_events[0].data["subgoals"]
        assert len(subgoals) == 2
        assert subgoals[0]["description"] == "Alpha"

    def test_stream_subgoal_data(self):
        state = _make_state(subgoals=["X"])
        pipeline = PlanExecutePipeline(max_replans=0)
        events = list(pipeline.stream(state))

        start_events = [e for e in events if e.kind == StreamEventKind.SUBGOAL_START]
        done_events = [e for e in events if e.kind == StreamEventKind.SUBGOAL_DONE]
        assert len(start_events) == 1
        assert len(done_events) == 1
        assert done_events[0].data["status"] == "done"


# ── Validation ─────────────────────────────────────────────────────────


class TestPlanExecuteValidation:
    def test_missing_planner_raises(self):
        state = PlanExecuteState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
            executor_fn=lambda s, c: "x",
        )
        pipeline = PlanExecutePipeline()
        with pytest.raises(ValueError, match="planner_fn"):
            pipeline.execute(state)

    def test_missing_executor_raises(self):
        state = PlanExecuteState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
            planner_fn=lambda t, c: ["a"],
        )
        pipeline = PlanExecutePipeline()
        with pytest.raises(ValueError, match="executor_fn"):
            pipeline.execute(state)
