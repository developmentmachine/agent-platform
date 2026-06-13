"""向后兼容 shim — recap-specific 副作用已迁入 agents.stock_recap.effects。

平台级副作用 (outbox) 仍留在本包。

.. deprecated::
    backtest/evolution 请直接从 ``agent_platform.agents.stock_recap.effects`` 导入。
"""
from __future__ import annotations

import warnings

from agent_platform.application.side_effects import outbox  # noqa: F401 — 平台级

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "agent_platform.application.side_effects backtest/evolution symbols are deprecated; "
            "import from agent_platform.agents.stock_recap.effects instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        _warned = True


def __getattr__(name: str):
    if name in {"load_recent_backtests_simple", "try_run_backtest"}:
        _warn()
        from agent_platform.agents.stock_recap.effects.backtest import (
            load_recent_backtests_simple,
            try_run_backtest,
        )

        return {
            "load_recent_backtests_simple": load_recent_backtests_simple,
            "try_run_backtest": try_run_backtest,
        }[name]
    if name == "run_deferred_evolution":
        _warn()
        from agent_platform.agents.stock_recap.effects.evolution import (
            run_deferred_evolution,
        )

        return run_deferred_evolution
    if name == "run_deferred_post_recap":
        _warn()
        from agent_platform.application.side_effects.deferred import (
            run_deferred_post_recap,
        )

        return run_deferred_post_recap
    raise AttributeError(name)


__all__ = [
    "load_recent_backtests_simple",
    "outbox",
    "run_deferred_evolution",
    "run_deferred_post_recap",
    "try_run_backtest",
]
