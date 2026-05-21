"""W3 起本包仅作 backwards-compat shim 聚合：所有 recap 业务已迁入
``agent_platform.agents.stock_recap.*``。lazy ``__getattr__`` 避免触发循环导入。
"""


def __getattr__(name: str):
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


__all__ = [
    "RecapAgent",
    "RecapAgentRunState",
    "execute_recap_pipeline",
    "generate_once",
    "iter_generate_ndjson",
]
