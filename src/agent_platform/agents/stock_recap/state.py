"""``RecapRunState`` —— stock-recap Agent 的 RunState 类型别名（W4）。

W4 选择：直接复用现有 ``RecapAgentRunState``，不强制套 ``core.orchestration.RunState``。
原因：``core.RunState`` 要求 ``principal: PrincipalContext`` 字段，而 recap 的
现有调用方都不传 — 不能在 W4 阶段引入破坏性字段。

W3 物理迁移后，这里改为真正的 ``@dataclass class RecapRunState(RunState)``，
追加业务字段并由 composition root 注入 ``principal``。
"""
from __future__ import annotations

from agent_platform.application.orchestration.context import RecapAgentRunState

# 类型别名：让上层代码可以写 ``Phase[RecapRunState]``，便于 W3 后迁移到独立类。
RecapRunState = RecapAgentRunState


__all__ = ["RecapRunState"]
