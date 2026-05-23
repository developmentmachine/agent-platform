"""Backward-compat shim → ``agent_platform.runtime.observability``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.runtime.observability")
sys.modules[__name__] = _real
