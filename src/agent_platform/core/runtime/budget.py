"""单次 Agent 运行预算（max_tool_calls / max_tokens / max_wall_ms）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent_platform.config.settings import Settings
from agent_platform.core.domain.models import LlmBudgetExceeded


@dataclass
class AgentBudget:
    """单次运行内累计资源用量与上限。"""

    max_tool_calls: int
    max_tokens: int
    max_wall_ms: int
    started_at_monotonic: float = field(default_factory=time.monotonic)
    tool_calls_used: int = 0
    tokens_used: int = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgentBudget":
        return cls(
            max_tool_calls=int(settings.agent_max_tool_calls),
            max_tokens=int(settings.agent_max_tokens),
            max_wall_ms=int(settings.agent_max_wall_ms),
        )

    def wall_ms_used(self) -> int:
        return int((time.monotonic() - self.started_at_monotonic) * 1000)

    def remaining_wall_ms(self) -> int:
        if self.max_wall_ms <= 0:
            return -1
        return max(0, self.max_wall_ms - self.wall_ms_used())

    def record_tool_call(self, n: int = 1) -> None:
        self.tool_calls_used += int(n)
        self.check()

    def record_tokens(self, n: int) -> None:
        self.tokens_used += int(n or 0)
        self.check()

    def check(self) -> None:
        if self.max_tool_calls > 0 and self.tool_calls_used > self.max_tool_calls:
            raise LlmBudgetExceeded(
                "tool_calls", limit=self.max_tool_calls, used=self.tool_calls_used
            )
        if self.max_tokens > 0 and self.tokens_used > self.max_tokens:
            raise LlmBudgetExceeded("tokens", limit=self.max_tokens, used=self.tokens_used)
        if self.max_wall_ms > 0:
            wall = self.wall_ms_used()
            if wall > self.max_wall_ms:
                raise LlmBudgetExceeded("wall_ms", limit=self.max_wall_ms, used=wall)


__all__ = ["AgentBudget"]
