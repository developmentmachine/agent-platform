"""Backward-compat shim → ``agent_platform.infra.memory``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.memory")
sys.modules[__name__] = _real
