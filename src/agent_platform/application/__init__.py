"""向后兼容 shim — 实际代码已迁入 agents.stock_recap.*。

.. deprecated::
    请直接 ``from agent_platform.agents.stock_recap import ...``。
    本模块的 lazy re-export 将在下个大版本移除。
"""
from __future__ import annotations

import warnings


def __getattr__(name: str):
    _warn()
    if name == "RecapAgent":
        from agent_platform.agents.stock_recap.agent import RecapAgent

        return RecapAgent
    if name == "RecapAgentRunState":
        from agent_platform.agents.stock_recap.recap_state import RecapAgentRunState

        return RecapAgentRunState
    if name == "execute_recap_pipeline":
        from agent_platform.agents.stock_recap.legacy_pipeline import (
            execute_recap_pipeline,
        )

        return execute_recap_pipeline
    if name == "generate_once":
        from agent_platform.agents.stock_recap.use_case import generate_once

        return generate_once
    if name == "iter_generate_ndjson":
        from agent_platform.agents.stock_recap.use_case import iter_generate_ndjson

        return iter_generate_ndjson
    raise AttributeError(name)


_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "agent_platform.application is deprecated; "
            "import from agent_platform.agents.stock_recap instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        _warned = True


__all__ = [
    "RecapAgent",
    "RecapAgentRunState",
    "execute_recap_pipeline",
    "generate_once",
    "iter_generate_ndjson",
]
