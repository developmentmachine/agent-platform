"""平台 application 层（W7 后）。

recap 业务已迁入 ``agent_platform.agents.stock_recap.*``；本包 ``__getattr__`` 仅保留
少量符号的 lazy re-export（``generate_once`` 等），供尚未改 import 的外部脚本过渡。
新代码请直接 import ``agents.stock_recap``。
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
