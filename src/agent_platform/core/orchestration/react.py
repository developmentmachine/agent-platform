"""ReActLoop — Thought → Action → Observation 循环编排原语。

ReAct (Reasoning + Acting) 认知架构：
1. Thought: LLM 推理下一步该做什么
2. Action: 执行工具调用或产出最终答案
3. Observation: 将工具结果反馈给 LLM
4. 重复直到 LLM 产出 final_answer 或达到最大迭代次数

使用方式：
    state = ReActState(
        run_ctx=ctx, principal=principal,
        task="查询今日A股涨跌情况",
        tools={"query_market_data": my_tool_fn},
        llm_caller=my_llm_fn,
        tool_parser=my_parser_fn,
    )
    loop = ReActLoop(max_iterations=5)
    loop.execute(state)
    print(state.final_answer)

所有 LLM/工具调用通过 state 上的注入函数完成（DI 模式），
不依赖任何 infra 实现。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.side_effects_bus import (
    SideEffectBus,
    SideEffectContext,
    StandardEvent,
)
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind

logger = logging.getLogger("agent_platform.core.orchestration.react")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# LLM caller: (messages) -> raw_text
LlmCaller = Callable[[List[Dict[str, str]]], str]

# Tool executor: (tool_name, tool_input) -> observation_text
ToolExecutor = Callable[[str, Dict[str, Any]], str]

# Tool parser: (llm_output) -> (thought, action_name, action_input, is_final, answer)
ToolParser = Callable[[str], Tuple[str, Optional[str], Optional[Dict[str, Any]], bool, Optional[str]]]


@dataclass
class ReActStep:
    """单步 ReAct 记录。"""
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None


@dataclass
class ReActState(RunState):
    """ReAct 循环的状态。

    Agent 在创建时注入：
    - task: 任务描述（第一条 user message）
    - tools: 工具名 → 执行函数的映射
    - llm_caller: LLM 调用函数
    - tool_parser: 解析 LLM 输出为 thought/action/answer 的函数
    """
    task: str = ""
    tools: Dict[str, ToolExecutor] = field(default_factory=dict)
    llm_caller: Optional[LlmCaller] = None
    tool_parser: Optional[ToolParser] = None
    # 系统提示（可选）
    system_prompt: str = ""
    # 结果
    steps: List[ReActStep] = field(default_factory=list)
    final_answer: Optional[str] = None
    messages: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default tool parser — 解析 "Thought: ...\nAction: ...\nAction Input: ..." 格式
# ---------------------------------------------------------------------------

def default_tool_parser(text: str) -> Tuple[str, Optional[str], Optional[Dict[str, Any]], bool, Optional[str]]:
    """解析 ReAct 格式的 LLM 输出。

    支持两种终态：
    - "Final Answer: xxx" → is_final=True
    - "Action: xxx\nAction Input: {...}" → 继续执行

    Returns:
        (thought, action_name, action_input, is_final, answer)
    """
    thought = ""
    action = None
    action_input = None
    is_final = False
    answer = None

    lines = text.strip().split("\n")
    current_section = "thought"

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Thought:"):
            thought = stripped[len("Thought:"):].strip()
            current_section = "thought"
        elif stripped.startswith("Final Answer:"):
            answer = stripped[len("Final Answer:"):].strip()
            is_final = True
            if not thought:
                thought = text.split("Final Answer:")[0].strip()
            return thought, None, None, True, answer
        elif stripped.startswith("Action:"):
            action = stripped[len("Action:"):].strip()
            current_section = "action"
        elif stripped.startswith("Action Input:"):
            raw = stripped[len("Action Input:"):].strip()
            try:
                action_input = json.loads(raw)
            except json.JSONDecodeError:
                action_input = {"query": raw}
            current_section = "input"
        elif current_section == "thought" and not thought:
            thought = stripped

    if action:
        return thought, action, action_input, False, None

    # 没有明确的 Action 或 Final Answer — 视为最终答案
    return thought, None, None, True, text.strip()


# ---------------------------------------------------------------------------
# ReActLoop
# ---------------------------------------------------------------------------

class ReActLoop:
    """Thought → Action → Observation 循环。

    与 Pipeline 接口对齐：提供 execute(state) 和 stream(state)。
    """

    def __init__(
        self,
        max_iterations: int = 5,
        *,
        side_effects: Optional[SideEffectBus] = None,
    ) -> None:
        self._max_iter = max_iterations
        self._bus = side_effects

    # ── 同步执行 ──────────────────────────────────────────────────────

    def execute(self, state: ReActState) -> None:
        """同步执行 ReAct 循环。"""
        self._validate(state)
        self._init_messages(state)

        for i in range(self._max_iter):
            step_idx = i + 1
            t0 = time.monotonic()

            # Thought + Action
            raw = state.llm_caller(state.messages)  # type: ignore[misc]
            thought, action, action_input, is_final, answer = self._parse(state, raw)

            step = ReActStep(thought=thought, action=action, action_input=action_input)

            if is_final:
                state.final_answer = answer or thought
                state.steps.append(step)
                self._log_step(step_idx, step, t0)
                self._emit_completed(state)
                return

            # Execute tool
            observation = self._execute_tool(state, action, action_input)  # type: ignore[arg-type]
            step.observation = observation
            state.steps.append(step)
            self._log_step(step_idx, step, t0)

            # Feed back into messages
            state.messages.append({"role": "assistant", "content": raw})
            state.messages.append({"role": "user", "content": f"Observation: {observation}"})

            # Budget check
            if isinstance(state, RunState) and state.budget is not None:
                state.budget.check()

        # Max iterations reached
        state.final_answer = state.steps[-1].thought if state.steps else "Max iterations reached"
        logger.warning("ReAct loop reached max_iterations=%d", self._max_iter)
        self._emit_completed(state)

    # ── 流式执行 ──────────────────────────────────────────────────────

    def stream(self, state: ReActState) -> Iterator[StreamEvent]:
        """流式执行 ReAct 循环，产出 StreamEvent。"""
        self._validate(state)
        self._init_messages(state)

        yield StreamEvent(kind=StreamEventKind.REACT_START, data={"task": state.task, "max_iterations": self._max_iter})

        for i in range(self._max_iter):
            step_idx = i + 1
            t0 = time.monotonic()

            yield StreamEvent(kind=StreamEventKind.REACT_THOUGHT_START, data={"step": step_idx})

            raw = state.llm_caller(state.messages)  # type: ignore[misc]
            thought, action, action_input, is_final, answer = self._parse(state, raw)

            step = ReActStep(thought=thought, action=action, action_input=action_input)

            yield StreamEvent(kind=StreamEventKind.REACT_THOUGHT_END, data={"step": step_idx, "thought": thought})

            if is_final:
                state.final_answer = answer or thought
                state.steps.append(step)
                yield StreamEvent(kind=StreamEventKind.REACT_ANSWER, data={"answer": state.final_answer})
                yield StreamEvent(kind=StreamEventKind.COMPLETED)
                self._emit_completed(state)
                return

            # Action
            yield StreamEvent(kind=StreamEventKind.REACT_ACTION, data={"step": step_idx, "action": action, "input": action_input})

            observation = self._execute_tool(state, action, action_input)  # type: ignore[arg-type]
            step.observation = observation
            state.steps.append(step)

            yield StreamEvent(kind=StreamEventKind.REACT_OBSERVATION, data={"step": step_idx, "observation": observation})

            # Feed back
            state.messages.append({"role": "assistant", "content": raw})
            state.messages.append({"role": "user", "content": f"Observation: {observation}"})

            self._log_step(step_idx, step, t0)

            if isinstance(state, RunState) and state.budget is not None:
                state.budget.check()

        state.final_answer = state.steps[-1].thought if state.steps else "Max iterations reached"
        yield StreamEvent(kind=StreamEventKind.REACT_ANSWER, data={"answer": state.final_answer})
        yield StreamEvent(kind=StreamEventKind.COMPLETED)
        self._emit_completed(state)

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _validate(self, state: ReActState) -> None:
        if not state.llm_caller:
            raise ValueError("ReActState.llm_caller is required")
        if not state.task:
            raise ValueError("ReActState.task is required")

    def _init_messages(self, state: ReActState) -> None:
        if state.messages:
            return
        if state.system_prompt:
            state.messages.append({"role": "system", "content": state.system_prompt})
        tool_desc = ", ".join(state.tools.keys()) if state.tools else "no tools"
        state.messages.append({
            "role": "user",
            "content": (
                f"{state.task}\n\n"
                f"Available tools: {tool_desc}\n"
                f"Use the format:\nThought: <reasoning>\nAction: <tool_name>\nAction Input: <json_input>\n\n"
                f"When you have the final answer:\nThought: <reasoning>\nFinal Answer: <answer>"
            ),
        })

    def _parse(self, state: ReActState, raw: str) -> Tuple[str, Optional[str], Optional[Dict[str, Any]], bool, Optional[str]]:
        parser = state.tool_parser or default_tool_parser
        return parser(raw)

    def _execute_tool(self, state: ReActState, name: str, input_data: Optional[Dict[str, Any]]) -> str:
        if name not in state.tools:
            return f"Error: unknown tool '{name}'. Available: {list(state.tools.keys())}"
        try:
            return state.tools[name](name, input_data or {})
        except Exception as e:
            return f"Error executing {name}: {e}"

    def _log_step(self, idx: int, step: ReActStep, t0: float) -> None:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("react step=%d action=%s duration_ms=%d", idx, step.action, duration_ms)

    def _emit_completed(self, state: ReActState) -> None:
        if self._bus is not None:
            self._bus.emit(
                StandardEvent.RUN_COMPLETED,
                SideEffectContext(
                    run_ctx=state.run_ctx,
                    principal=state.principal,
                    payload={"steps": len(state.steps)},
                ),
            )


__all__ = [
    "ReActLoop",
    "ReActState",
    "ReActStep",
    "LlmCaller",
    "ToolExecutor",
    "ToolParser",
    "default_tool_parser",
]
