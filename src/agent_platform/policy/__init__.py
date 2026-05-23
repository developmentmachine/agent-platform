"""Backward-compat shim → ``agent_platform.infra.guardrail``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.guardrail")
sys.modules[__name__] = _real
