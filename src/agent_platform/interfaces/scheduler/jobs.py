"""Shim → ``agent_platform.adapters.scheduler.jobs``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.adapters.scheduler.jobs")
sys.modules[__name__] = _real
