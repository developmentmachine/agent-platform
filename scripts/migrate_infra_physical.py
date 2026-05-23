#!/usr/bin/env python3
"""One-shot helper: rewrite imports after infrastructure/* → infra/* git mv."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_platform"

SUBPACKAGES = ("llm", "persistence", "memory", "push", "tools")

# Order matters: longest paths first within infra.*
REPLACEMENTS = [
    ("agent_platform.infrastructure.tools.handlers", "agent_platform.infra.tools.handlers"),
    ("agent_platform.infrastructure.tools", "agent_platform.infra.tools"),
    ("agent_platform.infrastructure.persistence", "agent_platform.infra.persistence"),
    ("agent_platform.infrastructure.memory", "agent_platform.infra.memory"),
    ("agent_platform.infrastructure.push", "agent_platform.infra.push"),
    ("agent_platform.infrastructure.llm", "agent_platform.infra.llm"),
    ("agent_platform.infrastructure.data", "agent_platform.infra.data"),
]

LOGGER_REPLACEMENTS = [
    ("agent_platform.infrastructure.", "agent_platform.infra."),
]


def iter_py_files() -> list[Path]:
    paths: list[Path] = []
    for base in (ROOT / "src", ROOT / "tests", ROOT / "docs"):
        if not base.exists():
            continue
        paths.extend(base.rglob("*.py"))
    return paths


def rewrite_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if path.is_relative_to(SRC / "infra"):
        for old, new in LOGGER_REPLACEMENTS:
            text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def write_shim_pkg(old_name: str, new_mod: str) -> None:
    """old_name e.g. 'llm' → infrastructure/llm/__init__.py aliases infra.llm."""
    pkg_dir = SRC / "infrastructure" / old_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    init = pkg_dir / "__init__.py"
    init.write_text(
        f'''"""Backward-compat shim → ``agent_platform.infra.{old_name}``."""
from __future__ import annotations

import importlib
import sys

_real = importlib.import_module("{new_mod}")
sys.modules[__name__] = _real
''',
        encoding="utf-8",
    )


def write_infra_data_shim() -> None:
    data_dir = SRC / "infra" / "data" / "sources"
    data_dir.mkdir(parents=True, exist_ok=True)
    init = data_dir / "__init__.py"
    if not init.exists():
        init.write_text(
            '"""Data sources shim → stock_recap agent data layer."""\n'
            "from agent_platform.agents.stock_recap.data.sources import *  # noqa: F401,F403\n",
            encoding="utf-8",
        )


def write_infrastructure_root() -> None:
    init = SRC / "infrastructure" / "__init__.py"
    init.write_text(
        '''"""Backward-compat shim for driven adapters (canonical: ``agent_platform.infra``)."""
from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = frozenset({"llm", "persistence", "memory", "push", "tools", "data"})


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"agent_platform.infra.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_SUBMODULES)
''',
        encoding="utf-8",
    )


def write_infra_init() -> None:
    init = SRC / "infra" / "__init__.py"
    init.write_text(
        '''"""infra — Driven Adapters：实现 ``core.ports`` 的具体技术细节。"""
from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = frozenset(
    {"llm", "persistence", "memory", "push", "tools", "mcp_client", "data"}
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"agent_platform.infra.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(_SUBMODULES)
''',
        encoding="utf-8",
    )


def main() -> int:
    changed = sum(1 for p in iter_py_files() if rewrite_file(p))
    for sub in SUBPACKAGES:
        write_shim_pkg(sub, f"agent_platform.infra.{sub}")
    write_infra_data_shim()
    write_infrastructure_root()
    write_infra_init()
    print(f"rewrote {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
