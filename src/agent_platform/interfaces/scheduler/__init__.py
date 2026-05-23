"""Shim → ``agent_platform.adapters.scheduler``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.adapters.scheduler")
sys.modules[__name__] = _real
