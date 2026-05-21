"""泛型编排引擎：与具体 Agent 解耦。

为兼容现有 ``application.orchestration`` 的入口（``execute_recap_pipeline`` /
``iter_recap_agent_ndjson`` / ``RecapAgentRunState``），后者保持不变，本子包仅
提供面向未来 Agent 的「平台级编排原语」。Recap 何时改用 ``Pipeline[RecapRunState]``
由后续 commit 决定，但新 Agent 必须从这里开始。
"""
from agent_platform.core.orchestration.run_state import RunState
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind
from agent_platform.core.orchestration.phase import Phase
from agent_platform.core.orchestration.pipeline import Pipeline, PipelineConfig
from agent_platform.core.orchestration.side_effects_bus import (
    SideEffectBus,
    SideEffectContext,
    SideEffectHandler,
    StandardEvent,
)

__all__ = [
    "RunState",
    "StreamEvent",
    "StreamEventKind",
    "Phase",
    "Pipeline",
    "PipelineConfig",
    "SideEffectBus",
    "SideEffectContext",
    "SideEffectHandler",
    "StandardEvent",
]
