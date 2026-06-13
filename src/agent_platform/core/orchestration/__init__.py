"""泛型编排引擎：与具体 Agent 解耦。

为兼容现有 ``application.orchestration`` 的入口（``execute_recap_pipeline`` /
``iter_recap_agent_ndjson`` / ``RecapAgentRunState``），后者保持不变，本子包仅
提供面向未来 Agent 的「平台级编排原语」。Recap 何时改用 ``Pipeline[RecapRunState]``
由后续 commit 决定，但新 Agent 必须从这里开始。

支持的认知架构：
- **Pipeline**: 线性 Phase 执行（stock-recap 使用）
- **ReActLoop**: Thought → Action → Observation 循环
- **PlanExecutePipeline**: Plan → Execute Subgoals → Replan
"""
from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind
from agent_platform.core.orchestration.phase import Phase
from agent_platform.core.orchestration.pipeline import Pipeline, PipelineConfig
from agent_platform.core.orchestration.react import (
    ReActLoop,
    ReActState,
    ReActStep,
    default_tool_parser,
)
from agent_platform.core.orchestration.plan_execute import (
    PlanExecutePipeline,
    PlanExecuteState,
    Subgoal,
    SubgoalStatus,
)
from agent_platform.core.orchestration.side_effects_bus import (
    SideEffectBus,
    SideEffectContext,
    SideEffectHandler,
    StandardEvent,
)

__all__ = [
    # Pipeline
    "RunState",
    "StreamEvent",
    "StreamEventKind",
    "Phase",
    "Pipeline",
    "PipelineConfig",
    # ReAct
    "ReActLoop",
    "ReActState",
    "ReActStep",
    "default_tool_parser",
    # Plan-and-Execute
    "PlanExecutePipeline",
    "PlanExecuteState",
    "Subgoal",
    "SubgoalStatus",
    # Side effects
    "SideEffectBus",
    "SideEffectContext",
    "SideEffectHandler",
    "StandardEvent",
]
