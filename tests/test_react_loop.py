"""Tests for ReActLoop orchestration primitive."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from agent_platform.core.orchestration.react import (
    ReActLoop,
    ReActState,
    ReActStep,
    default_tool_parser,
)
from agent_platform.core.orchestration.stream_events import StreamEventKind
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext


def _make_state(
    *,
    task: str = "What is 2+2?",
    llm_responses: Optional[List[str]] = None,
    tools: Optional[Dict[str, Any]] = None,
    system_prompt: str = "",
) -> ReActState:
    """Create a test ReActState with mock LLM and tools."""
    responses = llm_responses or ["Thought: I know the answer\nFinal Answer: 4"]
    call_idx = {"i": 0}

    def mock_llm(messages: List[Dict[str, str]]) -> str:
        idx = call_idx["i"]
        call_idx["i"] += 1
        return responses[min(idx, len(responses) - 1)]

    def mock_tool(name: str, input_data: Dict[str, Any]) -> str:
        return f"Tool {name} result for {input_data}"

    return ReActState(
        run_ctx=RunContext.new(),
        principal=PrincipalContext.anonymous(source="test"),
        task=task,
        llm_caller=mock_llm,
        tools=tools or {},
        system_prompt=system_prompt,
    )


# ── default_tool_parser ────────────────────────────────────────────────


class TestDefaultToolParser:
    def test_parse_final_answer(self):
        text = "Thought: I know the answer\nFinal Answer: 42"
        thought, action, action_input, is_final, answer = default_tool_parser(text)
        assert is_final is True
        assert answer == "42"
        assert action is None

    def test_parse_action(self):
        text = 'Thought: Need to search\nAction: web_search\nAction Input: {"query": "hello"}'
        thought, action, action_input, is_final, answer = default_tool_parser(text)
        assert is_final is False
        assert action == "web_search"
        assert action_input == {"query": "hello"}

    def test_parse_plain_text_as_final(self):
        text = "Just a plain answer"
        thought, action, action_input, is_final, answer = default_tool_parser(text)
        assert is_final is True
        assert answer == "Just a plain answer"

    def test_parse_action_input_non_json(self):
        text = "Thought: search\nAction: search\nAction Input: hello world"
        _, action, action_input, is_final, _ = default_tool_parser(text)
        assert is_final is False
        assert action == "search"
        assert action_input == {"query": "hello world"}


# ── ReActLoop.execute ──────────────────────────────────────────────────


class TestReActExecute:
    def test_single_step_final_answer(self):
        state = _make_state(llm_responses=["Thought: Simple math\nFinal Answer: 4"])
        loop = ReActLoop(max_iterations=5)
        loop.execute(state)

        assert state.final_answer == "4"
        assert len(state.steps) == 1
        assert state.steps[0].thought == "Simple math"

    def test_multi_step_with_tool(self):
        responses = [
            'Thought: Need data\nAction: search\nAction Input: {"q": "test"}',
            "Thought: Got data\nFinal Answer: The answer is 42",
        ]
        state = _make_state(
            task="Find the answer",
            llm_responses=responses,
            tools={"search": lambda name, inp: "search results"},
        )
        loop = ReActLoop(max_iterations=5)
        loop.execute(state)

        assert state.final_answer == "The answer is 42"
        assert len(state.steps) == 2
        assert state.steps[0].action == "search"
        assert state.steps[0].observation == "search results"

    def test_max_iterations_reached(self):
        responses = [
            'Thought: step 1\nAction: tool1\nAction Input: {"a": 1}',
            'Thought: step 2\nAction: tool1\nAction Input: {"a": 2}',
            'Thought: step 3\nAction: tool1\nAction Input: {"a": 3}',
        ]
        state = _make_state(
            task="infinite loop",
            llm_responses=responses,
            tools={"tool1": lambda n, i: "result"},
        )
        loop = ReActLoop(max_iterations=3)
        loop.execute(state)

        assert len(state.steps) == 3
        assert state.final_answer is not None

    def test_unknown_tool_returns_error(self):
        responses = [
            'Thought: oops\nAction: nonexistent\nAction Input: {}',
            "Thought: ok\nFinal Answer: done",
        ]
        state = _make_state(llm_responses=responses, tools={})
        loop = ReActLoop(max_iterations=5)
        loop.execute(state)

        assert "unknown tool" in state.steps[0].observation
        assert state.final_answer == "done"

    def test_tool_exception_caught(self):
        def bad_tool(name, inp):
            raise ValueError("boom")

        responses = [
            'Thought: try\nAction: bad\nAction Input: {}',
            "Thought: recovered\nFinal Answer: ok",
        ]
        state = _make_state(llm_responses=responses, tools={"bad": bad_tool})
        loop = ReActLoop(max_iterations=5)
        loop.execute(state)

        assert "Error executing bad" in state.steps[0].observation


# ── ReActLoop.stream ───────────────────────────────────────────────────


class TestReActStream:
    def test_stream_events_order(self):
        state = _make_state(
            llm_responses=[
                'Thought: need info\nAction: search\nAction Input: {"q": "x"}',
                "Thought: done\nFinal Answer: result",
            ],
            tools={"search": lambda n, i: "data"},
        )
        loop = ReActLoop(max_iterations=5)
        events = list(loop.stream(state))

        kinds = [e.kind for e in events]
        assert StreamEventKind.REACT_START in kinds
        assert StreamEventKind.REACT_THOUGHT_START in kinds
        assert StreamEventKind.REACT_THOUGHT_END in kinds
        assert StreamEventKind.REACT_ACTION in kinds
        assert StreamEventKind.REACT_OBSERVATION in kinds
        assert StreamEventKind.REACT_ANSWER in kinds
        assert StreamEventKind.COMPLETED in kinds

    def test_stream_single_step_final(self):
        state = _make_state(llm_responses=["Thought: easy\nFinal Answer: yes"])
        loop = ReActLoop(max_iterations=5)
        events = list(loop.stream(state))

        # Should have: START, THOUGHT_START, THOUGHT_END, ANSWER, COMPLETED
        # No ACTION or OBSERVATION
        kinds = [e.kind for e in events]
        assert StreamEventKind.REACT_ACTION not in kinds
        assert StreamEventKind.REACT_OBSERVATION not in kinds


# ── Validation ─────────────────────────────────────────────────────────


class TestReActValidation:
    def test_missing_llm_caller_raises(self):
        state = ReActState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            task="test",
        )
        loop = ReActLoop()
        with pytest.raises(ValueError, match="llm_caller"):
            loop.execute(state)

    def test_missing_task_raises(self):
        state = ReActState(
            run_ctx=RunContext.new(),
            principal=PrincipalContext.anonymous(source="test"),
            llm_caller=lambda msgs: "answer",
        )
        loop = ReActLoop()
        with pytest.raises(ValueError, match="task"):
            loop.execute(state)
