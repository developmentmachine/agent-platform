"""Backward-compat shim → ``agent_platform.infra.push``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.push")
sys.modules[__name__] = _real
