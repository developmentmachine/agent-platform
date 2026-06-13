"""向后兼容 shim — 实际代码已迁入 agents.stock_recap.memory.manager。

.. deprecated::
    请直接 ``from agent_platform.agents.stock_recap.memory.manager import ...``。
    本模块将在下个大版本移除。
"""
from __future__ import annotations

import warnings

warnings.warn(
    "agent_platform.application.memory is deprecated; "
    "import from agent_platform.agents.stock_recap.memory.manager instead.",
    DeprecationWarning,
    stacklevel=2,
)

from agent_platform.agents.stock_recap.memory.manager import (  # noqa: F401
    check_and_run_evolution,
    extract_market_patterns,
    get_prompt_version,
    load_evolution_guidance,
    load_recent_memory,
)

__all__ = [
    "check_and_run_evolution",
    "extract_market_patterns",
    "get_prompt_version",
    "load_evolution_guidance",
    "load_recent_memory",
]
