"""Backward-compat shim → ``agent_platform.infra.persistence``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.infra.persistence")
sys.modules[__name__] = _real
