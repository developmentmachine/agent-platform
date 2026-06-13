"""Compatibility shim — re-exports from agent_platform.core.runtime.agent_scope."""
from agent_platform.core.runtime.agent_scope import *  # noqa: F401,F403
from agent_platform.core.runtime.agent_scope import (  # noqa: F401
    agent_execution,
    agent_execution_for_id,
    require_agent_scope,
)
