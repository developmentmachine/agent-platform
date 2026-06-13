"""向后兼容 shim — 实际代码已迁入 agents.stock_recap.*。

.. deprecated::
    请直接 ``from agent_platform.agents.stock_recap.legacy_pipeline import ...``。
"""
from __future__ import annotations

import warnings

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "agent_platform.application.orchestration is deprecated; "
            "import from agent_platform.agents.stock_recap.legacy_pipeline instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        _warned = True


def __getattr__(name: str):
    _warn()
    if name == "RecapAgentRunState":
        from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState

        return RecapAgentRunState
    if name == "execute_recap_pipeline":
        from agent_platform.agents.stock_recap.legacy_pipeline import (
            execute_recap_pipeline,
        )

        return execute_recap_pipeline
    if name == "iter_recap_agent_ndjson":
        from agent_platform.agents.stock_recap.legacy_pipeline import (
            iter_recap_agent_ndjson,
        )

        return iter_recap_agent_ndjson
    raise AttributeError(name)


__all__ = ["RecapAgentRunState", "execute_recap_pipeline", "iter_recap_agent_ndjson"]
