"""Backward-compat shim → ``agent_platform.infra.llm``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.llm")
sys.modules[__name__] = _real
