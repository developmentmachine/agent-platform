"""Shim → ``agent_platform.adapters.cli.main``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.adapters.cli.main")
sys.modules[__name__] = _real
