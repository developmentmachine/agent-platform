"""Backward-compat shim → ``agent_platform.infra.tools``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.tools")
sys.modules[__name__] = _real
