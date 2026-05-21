"""Composition Root — apps 只能通过本子包获取 AgentRuntime。

Apps **禁止**：
- 直接 import ``agent_platform.infra.*``；
- 直接 import ``agent_platform.agents.*``（agent 实例由 ``AgentRuntime`` 提供）；
- 直接 ``new`` 任意 ChatUseCase / Pipeline。

只允许 ::

    from agent_platform.runtime import create_runtime, AgentRuntime
    runtime = create_runtime(settings)
    result = runtime.run(agent_id="stock-recap", payload={...}, principal=...)

下层（infra / agents / 默认实现）的替换都集中在 ``factory.create_runtime``。
"""
from agent_platform.runtime.agent_runtime import AgentRuntime, AgentRuntimeOverrides
from agent_platform.runtime.factory import create_runtime
from agent_platform.runtime.session_resolver import StatelessSessionResolver

__all__ = [
    "AgentRuntime",
    "AgentRuntimeOverrides",
    "create_runtime",
    "StatelessSessionResolver",
]
