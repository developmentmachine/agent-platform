"""平台级 NDJSON 流事件模型 — 所有 Agent 的流式输出共用一套包络。

具体字段沿用现有 recap 流的命名（``event`` / ``data``），便于 adapter 透传。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict


class StreamEventKind(str, Enum):
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    PHASE_PROGRESS = "phase_progress"
    AGENT_OUTPUT = "agent_output"
    ERROR = "error"
    COMPLETED = "completed"

    # ReAct events
    REACT_START = "react_start"
    REACT_THOUGHT_START = "react_thought_start"
    REACT_THOUGHT_END = "react_thought_end"
    REACT_ACTION = "react_action"
    REACT_OBSERVATION = "react_observation"
    REACT_ANSWER = "react_answer"

    # Plan-and-Execute events
    PLAN_GENERATED = "plan_generated"
    SUBGOAL_START = "subgoal_start"
    SUBGOAL_DONE = "subgoal_done"
    REPLAN = "replan"


@dataclass
class StreamEvent:
    kind: StreamEventKind
    phase: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


__all__ = ["StreamEvent", "StreamEventKind"]
