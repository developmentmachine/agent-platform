"""向后兼容 shim — 已拆分到 agents.stock_recap.effects。

.. deprecated::
    请直接从 ``agent_platform.agents.stock_recap.effects`` 导入。
"""
from __future__ import annotations

import warnings

warnings.warn(
    "agent_platform.application.recap_support is deprecated; "
    "import from agent_platform.agents.stock_recap.effects instead.",
    DeprecationWarning,
    stacklevel=2,
)

from agent_platform.agents.stock_recap.effects.backtest import (  # noqa: F401
    load_recent_backtests_simple,
    try_run_backtest,
)
from agent_platform.agents.stock_recap.effects.deferred import (  # noqa: F401
    run_deferred_post_recap,
)

__all__ = [
    "load_recent_backtests_simple",
    "run_deferred_post_recap",
    "try_run_backtest",
]
