"""从包内资源加载 prompt 文本与 manifest（可版本化、可审计）。

W3 起本 loader 兼容**多 bundle 叠加**：
- **平台底座**：``agent_platform.resources.prompts``（保留通用 ``json_output_instruction`` 之类）；
- **Agent bundle**（推荐用法）：第三方 / 业务包通过 ``pyproject.toml`` 登记::

      [project.entry-points."agent_platform.prompts"]
      stock_recap = "agent_platform.agents.stock_recap.prompts:bundle_root"

  ``bundle_root`` 可为 ``Path`` / ``str``，或 ``() -> Path | str`` 无参可调用，
  指向含 ``manifest.json`` 的 bundle 根目录。

合并规则：
- ``artifacts``：按 key 合并；先底座，后 entry_points；后写覆盖先写。
- ``bundle_version``：依然取**平台底座**的版本字符串以保证 prompt_version 稳定。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import metadata
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agent_platform.resources.prompts.loader")

_PKG = "agent_platform.resources.prompts"
_ENTRY_GROUP = "agent_platform.prompts"


# (artifacts_map, root_path_or_None) 列表，None 表示平台包内资源（用 importlib.resources）。
_OVERLAY_CACHE: Optional[List[Tuple[Dict[str, str], Optional[Path]]]] = None
_OVERLAY_FP: Optional[Tuple[Any, ...]] = None


def clear_prompt_cache() -> None:
    """使叠加 manifest 与 artifact 文本缓存失效（测试 / 热加载用）。"""
    global _OVERLAY_CACHE, _OVERLAY_FP
    _OVERLAY_CACHE = None
    _OVERLAY_FP = None
    _base_manifest.cache_clear()
    load_prompt_artifact.cache_clear()


@lru_cache(maxsize=1)
def _base_manifest() -> dict:
    raw = files(_PKG).joinpath("manifest.json").read_text(encoding="utf-8")
    return json.loads(raw)


def prompt_bundle_version() -> str:
    return str(_base_manifest()["bundle_version"])


def _iter_entry_point_bundle_roots() -> List[Path]:
    roots: List[Path] = []
    try:
        eps = metadata.entry_points()
        selected = (
            eps.select(group=_ENTRY_GROUP)
            if hasattr(eps, "select")
            else eps.get(_ENTRY_GROUP, ())
        )
    except Exception as e:
        logger.debug("entry_points(%s) skipped: %s", _ENTRY_GROUP, e)
        return roots
    for ep in selected:
        try:
            obj = ep.load()
            out = obj() if callable(obj) else obj
            root = Path(out).resolve()
        except Exception as e:
            logger.warning("bad prompts bundle root from %s: %s", ep.name, e)
            continue
        if root.is_dir():
            roots.append(root)
        else:
            logger.warning("prompts bundle root not a directory: %s (%s)", root, ep.name)
    return roots


def _fingerprint() -> Tuple[Any, ...]:
    try:
        eps = metadata.entry_points()
        selected = (
            eps.select(group=_ENTRY_GROUP)
            if hasattr(eps, "select")
            else eps.get(_ENTRY_GROUP, ())
        )
        ep_sig = tuple((ep.name, ep.value) for ep in sorted(selected, key=lambda x: x.name))
    except Exception:
        ep_sig = ()
    mtimes = []
    for root in _iter_entry_point_bundle_roots():
        mf = root / "manifest.json"
        try:
            mtimes.append((str(mf), mf.stat().st_mtime_ns if mf.is_file() else -1))
        except OSError:
            mtimes.append((str(mf), -2))
    return (ep_sig, tuple(mtimes))


def _build_overlays() -> List[Tuple[Dict[str, str], Optional[Path]]]:
    global _OVERLAY_CACHE, _OVERLAY_FP
    fp = _fingerprint()
    if _OVERLAY_CACHE is not None and fp == _OVERLAY_FP:
        return _OVERLAY_CACHE
    overlays: List[Tuple[Dict[str, str], Optional[Path]]] = []
    base_artifacts = dict(_base_manifest().get("artifacts") or {})
    overlays.append((base_artifacts, None))
    for root in _iter_entry_point_bundle_roots():
        mf = root / "manifest.json"
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            arts = dict(data.get("artifacts") or {})
        except Exception as e:
            logger.warning("skip invalid prompts bundle %s: %s", root, e)
            continue
        overlays.append((arts, root))
    _OVERLAY_CACHE = overlays
    _OVERLAY_FP = fp
    return overlays


def _resolve_artifact(name: str) -> Tuple[str, Optional[Path]]:
    """返回 (相对路径, bundle_root)；root=None 表示平台包内资源。后写覆盖先写。"""
    chosen: Optional[Tuple[str, Optional[Path]]] = None
    for arts, root in _build_overlays():
        rel = arts.get(name)
        if rel:
            chosen = (str(rel), root)
    if chosen is None:
        raise KeyError(f"unknown prompt artifact: {name}")
    return chosen


@lru_cache(maxsize=32)
def load_prompt_artifact(name: str) -> str:
    """name 为 manifest.artifacts 的 key，如 ``system_recap``。"""
    rel, root = _resolve_artifact(name)
    if root is None:
        return files(_PKG).joinpath(rel).read_text(encoding="utf-8")
    return (root / rel).read_text(encoding="utf-8")


def system_recap_base() -> str:
    return load_prompt_artifact("system_recap").strip()


def pattern_extraction_system() -> str:
    return load_prompt_artifact("pattern_extraction_system").strip()


def json_output_instruction() -> str:
    return load_prompt_artifact("json_output_instruction").strip()


PROMPT_BASE_VERSION: str = prompt_bundle_version()
