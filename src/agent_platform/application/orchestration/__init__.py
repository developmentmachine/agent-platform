"""Agent 编排：W3 起为 ``agents.stock_recap`` 的 shim；lazy 避免循环导入。"""


def __getattr__(name: str):
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
