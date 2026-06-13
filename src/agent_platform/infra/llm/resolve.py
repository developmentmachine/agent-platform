"""Compatibility shim — re-exports from agent_platform."""
from agent_platform.core.config.resolve import *  # noqa: F401,F403

from agent_platform.core.config.resolve import (
    _interpret_model_spec,
    _model_prefix_to_backend,
    llm_backend_effective,
    model_effective,
)
