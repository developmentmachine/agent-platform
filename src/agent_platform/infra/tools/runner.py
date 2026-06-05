"""``RecapToolRunner`` —— **W2 起改为 ``runtime.McpToolGateway`` 的薄包装**。

为什么保留这个类名而不直接 import McpToolGateway：
- 大量调用方（providers / pipeline）以 ``RecapToolRunner`` 名字下穿；
- 测试 fixture 也以此名 mock；
- 全面切换在 W6 / W7 完成，这一层 shim 让 W2 commit 完全零回归。

唯一行为变化：底层执行从「本地 function-calling 注册表」改为「走 McpClientPort
（默认 InProcessMcpClient，零子进程开销）」；schemas 由 ``list_tools`` 推导，
不再有双写。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from agent_platform.config.settings import Settings
from agent_platform.infra.mcp_client.inproc import InProcessMcpClient
from agent_platform.infra.policy.tools import (
    ToolBudgetExceeded,
    ToolDisabled,
    ToolForbidden,
    ToolNotRegistered,
    ToolPolicyError,
    ToolPolicyRegistry,
    ToolTimeout,
)
from agent_platform.runtime.mcp_gateway import McpToolGateway

logger = logging.getLogger("agent_platform.infra.tools.runner")


class RecapToolRunner:
    """与 W1 之前等价的对外 API（薄包装于 ``McpToolGateway``）。

    任何新代码请直接使用 ``runtime.McpToolGateway`` + ``infra.mcp_client.InProcessMcpClient``。
    """

    __slots__ = ("_gateway",)

    def __init__(
        self,
        settings: Settings,
        policy_registry: Optional[ToolPolicyRegistry] = None,
    ) -> None:
        client = InProcessMcpClient()
        self._gateway = McpToolGateway(settings, client, policy_registry=policy_registry)

    # ─── 元信息 ───────────────────────────────────────────────────────────

    @property
    def tools_enabled(self) -> bool:
        return self._gateway.tools_enabled

    @property
    def policy_registry(self) -> ToolPolicyRegistry:
        return self._gateway.policy_registry

    def enabled_tool_names(self) -> Set[str]:
        return self._gateway.enabled_tool_names()

    def openai_compatible_schemas(self) -> List[Dict[str, Any]]:
        return self._gateway.openai_compatible_schemas()

    # ─── 单次执行 ─────────────────────────────────────────────────────────

    def execute(self, name: str, arguments: Dict[str, Any], db_path: str) -> str:
        return self._gateway.execute(name, arguments, db_path)

    # ─── 预取 ─────────────────────────────────────────────────────────────

    def prefetch_for_prompt(self, date: str, db_path: str) -> str:
        return self._gateway.prefetch_for_prompt(date, db_path)


__all__ = [
    "RecapToolRunner",
    "ToolBudgetExceeded",
    "ToolDisabled",
    "ToolForbidden",
    "ToolNotRegistered",
    "ToolPolicyError",
    "ToolTimeout",
]
