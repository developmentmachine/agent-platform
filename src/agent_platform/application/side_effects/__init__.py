"""W3 起：recap-specific 副作用 (backtest/evolution/push) 物理迁入
``agents.stock_recap.effects``；本包保留 platform-level 副作用 (outbox/deferred)
与 lazy shim attribute resolution。
"""
from agent_platform.application.side_effects import outbox  # noqa: F401 — 平台级


def __getattr__(name: str):
    if name in {"load_recent_backtests_simple", "try_run_backtest"}:
        from agent_platform.agents.stock_recap.effects.backtest import (
            load_recent_backtests_simple,
            try_run_backtest,
        )

        return {
            "load_recent_backtests_simple": load_recent_backtests_simple,
            "try_run_backtest": try_run_backtest,
        }[name]
    if name == "run_deferred_evolution":
        from agent_platform.agents.stock_recap.effects.evolution import (
            run_deferred_evolution,
        )

        return run_deferred_evolution
    if name == "run_deferred_post_recap":
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
