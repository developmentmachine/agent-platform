#!/usr/bin/env python3
"""Rewrite imports after interfaces/* → adapters/* git mv."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_platform"

REPLACEMENTS = [
    ("agent_platform.interfaces.api", "agent_platform.adapters.http.api"),
    ("agent_platform.interfaces.scheduler.jobs", "agent_platform.adapters.scheduler.jobs"),
    ("agent_platform.interfaces.scheduler", "agent_platform.adapters.scheduler"),
    ("agent_platform.interfaces.mcp_stdio", "agent_platform.adapters.mcp_stdio.main"),
    ("agent_platform.interfaces.cli", "agent_platform.adapters.cli.main"),
    ("agent_platform.interfaces.agents", "agent_platform.adapters.cli.agents"),
]

LOGGER_PREFIX = [
    ("agent_platform.interfaces.", "agent_platform.adapters."),
]


def iter_py_files() -> list[Path]:
    paths: list[Path] = []
    for base in (ROOT / "src", ROOT / "tests", ROOT / "docs", ROOT / "pyproject.toml"):
        if base.is_file():
            paths.append(base)
            continue
        if base.exists():
            paths.extend(base.rglob("*.py"))
    return paths


def rewrite_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if path.suffix == ".py" and (
        "adapters/http" in str(path)
        or "adapters/cli" in str(path)
        or "adapters/scheduler" in str(path)
        or "adapters/mcp_stdio" in str(path)
    ):
        for old, new in LOGGER_PREFIX:
            text = text.replace(old, new)
    if path.name == "pyproject.toml":
        text = text.replace(
            "agent_platform.interfaces.cli:cli_main",
            "agent_platform.adapters.cli:cli_main",
        )
        text = text.replace(
            "agent_platform.interfaces.mcp_stdio:main",
            "agent_platform.adapters.mcp_stdio:main",
        )
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def write_interfaces_shims() -> None:
    iface = SRC / "interfaces"
    iface.mkdir(exist_ok=True)
    (iface / "__init__.py").write_text(
        '''"""Backward-compat shim (canonical: ``agent_platform.adapters``)."""
from __future__ import annotations

import importlib
from typing import Any

_ALIASES = {
    "cli": "agent_platform.adapters.cli.main",
    "mcp_stdio": "agent_platform.adapters.mcp_stdio.main",
}


def __getattr__(name: str) -> Any:
    if name == "api":
        return importlib.import_module("agent_platform.adapters.http.api")
    if name in _ALIASES:
        return importlib.import_module(_ALIASES[name])
    if name == "scheduler":
        return importlib.import_module("agent_platform.adapters.scheduler")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
''',
        encoding="utf-8",
    )

    api_pkg = iface / "api"
    api_pkg.mkdir(exist_ok=True)
    (api_pkg / "__init__.py").write_text(
        '''"""Shim → ``agent_platform.adapters.http.api``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.adapters.http.api")
sys.modules[__name__] = _real
''',
        encoding="utf-8",
    )

    sched = iface / "scheduler"
    sched.mkdir(exist_ok=True)
    (sched / "__init__.py").write_text(
        '''"""Shim → ``agent_platform.adapters.scheduler``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("agent_platform.adapters.scheduler")
sys.modules[__name__] = _real
''',
        encoding="utf-8",
    )

    agents = iface / "agents"
    agents.mkdir(exist_ok=True)
    (agents / "__init__.py").write_text(
        '"""Shim → ``agent_platform.adapters.cli.agents``."""\n'
        "from agent_platform.adapters.cli.agents import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )


def write_adapter_inits() -> None:
    (SRC / "adapters" / "http" / "__init__.py").write_text(
        '''"""HTTP adapter — FastAPI 入口（按 AgentRegistry 自动装配路由）。"""
from agent_platform.adapters.http.api.app import app, create_app

__all__ = ["app", "create_app"]
''',
        encoding="utf-8",
    )
    (SRC / "adapters" / "cli" / "__init__.py").write_text(
        '''"""CLI adapter — 按 AgentRegistry 自动发现子命令。"""
from agent_platform.adapters.cli.main import cli_main

__all__ = ["cli_main"]
''',
        encoding="utf-8",
    )
    (SRC / "adapters" / "scheduler" / "__init__.py").write_text(
        '''"""调度 adapter — APScheduler 定时触发（按 AgentRegistry 自动绑定 cron）。"""
from agent_platform.adapters.scheduler.jobs import start_scheduler

__all__ = ["start_scheduler"]
''',
        encoding="utf-8",
    )
    (SRC / "adapters" / "mcp_stdio" / "__init__.py").write_text(
        '''"""MCP stdio adapter — Agent 能力的 MCP 暴露入口。"""
from agent_platform.adapters.mcp_stdio.main import main

__all__ = ["main"]
''',
        encoding="utf-8",
    )


def main() -> int:
    changed = sum(1 for p in iter_py_files() if rewrite_file(p))
    write_interfaces_shims()
    write_adapter_inits()
    print(f"rewrote {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
