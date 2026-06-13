"""向后兼容 shim — 实际代码在 agents.stock_recap.effects.deferred。

.. deprecated::
    请直接 ``from agent_platform.agents.stock_recap.effects.deferred import ...``。
"""
from __future__ import annotations

import warnings

warnings.warn(
    "agent_platform.application.side_effects.deferred is deprecated; "
    "import from agent_platform.agents.stock_recap.effects.deferred instead.",
    DeprecationWarning,
    stacklevel=2,
)

from agent_platform.agents.stock_recap.effects.deferred import *  # noqa: F401,F403
