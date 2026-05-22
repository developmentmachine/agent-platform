"""RunState 基类 — 各 Agent 自定义 RunState 时继承此类。

只放跨 Agent 的稳定字段；业务字段由子类追加。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_platform.core.runtime.budget import AgentBudget
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.session import SessionContext


@dataclass
class RunState:
    """所有 Agent RunState 的最小公分母。"""

    run_ctx: RunContext
    principal: PrincipalContext
    session: Optional[SessionContext] = None
    budget: Optional[AgentBudget] = None
    started_at_monotonic: float = 0.0
    errors: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def request_id(self) -> str:
        return self.run_ctx.request_id

    @property
    def trace_id(self) -> str:
        return self.run_ctx.trace_id


__all__ = ["RunState"]
