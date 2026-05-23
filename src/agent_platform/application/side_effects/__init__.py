"""Backward-compat facade：平台副作用在 ``runtime.side_effects``，recap 动作在 agents。"""
from agent_platform.runtime.side_effects import outbox  # noqa: F401
from agent_platform.runtime.side_effects.deferred import run_deferred_post_recap


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
    raise AttributeError(name)


__all__ = [
    "load_recent_backtests_simple",
    "outbox",
    "run_deferred_evolution",
    "run_deferred_post_recap",
    "try_run_backtest",
]
