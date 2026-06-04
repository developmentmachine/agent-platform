"""Skill bundle 声明层 — Agent 注册表与 skill bundle 之间的桥梁。

分层约定（skill id 唯一真源）：
- **Skill id**：仅来自各 ``SKILL.md`` frontmatter 的 ``name``（加载时自动解析）；
- **manifest.json**：只登记 ``path``（及可选 ``description``）、``mode_to_skill_id``；
  **禁止**在 manifest 里写 ``id``，避免与 ``name`` 双份维护；
- **加载**：``enrich_bundle_manifest`` 为合并表注入解析后的 ``id``；
- **注册**：``with_skill_bundle`` 从 enriched manifest 推导 ``AgentDefinition`` 字段。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agent_platform.core.registry.agent_definition import AgentDefinition
from agent_platform.skills.loader import parse_skill_markdown

logger = logging.getLogger("agent_platform.skills.bundle")

_ENTRY_GROUP = "agent_platform.skills"
BundleRoot = Union[Path, str]


@dataclass(frozen=True)
class SkillBundleEntry:
    """解析后的单条 skill（id 来自 SKILL.md ``name``）。"""

    skill_id: str
    path: str


@dataclass(frozen=True)
class SkillBundleManifest:
    """单个 bundle 根目录 manifest 的解析结果（未与平台底座合并）。"""

    bundle_version: str
    skill_ids: tuple[str, ...]
    entries: tuple[SkillBundleEntry, ...]
    mode_to_skill_id: Dict[str, str]
    root: Path

    @property
    def skill_id_set(self) -> set[str]:
        return set(self.skill_ids)


def resolve_skill_id_from_path(bundle_root: BundleRoot, rel_path: str) -> str:
    """从 ``SKILL.md`` frontmatter 读取 skill id（``name`` 字段）。"""
    root = Path(bundle_root).resolve()
    md_path = root / rel_path
    if not md_path.is_file():
        raise FileNotFoundError(f"SKILL.md not found: {md_path}")
    meta, _ = parse_skill_markdown(md_path.read_text(encoding="utf-8"))
    name = (meta.get("name") or "").strip()
    if not name:
        raise ValueError(
            f"SKILL.md frontmatter must define 'name' (skill id): {rel_path} under {root}"
        )
    return name


def enrich_bundle_manifest(bundle_root: BundleRoot, raw: Dict[str, Any]) -> Dict[str, Any]:
    """解析 bundle manifest：为每条 skill 注入 ``id``（来自 ``SKILL.md`` ``name``）。

    ``skills`` 条目可为：
    - 字符串：相对 ``path``；
    - 对象：``{"path": "...", "description": "..."}``（不得含 ``id``）。

    返回的 dict 供 ``skills.loader`` 合并；其中的 ``id`` 为运行时派生字段，非作者手写。
    """
    root = Path(bundle_root).resolve()
    out = json.loads(json.dumps(raw))
    errors: List[str] = []
    enriched: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in out.get("skills") or []:
        if isinstance(item, str):
            rel = item.strip()
            desc = ""
            legacy_id: Optional[str] = None
        elif isinstance(item, dict):
            rel = str(item.get("path", "")).strip()
            desc = str(item.get("description", "")).strip()
            legacy_id = str(item.get("id", "")).strip() or None
        else:
            errors.append(f"invalid skill entry type: {type(item).__name__}")
            continue

        if not rel:
            errors.append("skill entry missing path")
            continue
        if legacy_id is not None:
            errors.append(
                f"{rel}: manifest must not include 'id' (got {legacy_id!r}); "
                "skill id is defined only by SKILL.md frontmatter 'name'"
            )
            continue

        try:
            skill_id = resolve_skill_id_from_path(root, rel)
        except (FileNotFoundError, ValueError, OSError) as e:
            errors.append(f"{rel}: {e}")
            continue

        if skill_id in seen_ids:
            errors.append(f"duplicate skill id {skill_id!r} (path {rel})")
            continue
        seen_ids.add(skill_id)
        entry: Dict[str, Any] = {"id": skill_id, "path": rel}
        if desc:
            entry["description"] = desc
        enriched.append(entry)

    modes = {str(k): str(v) for k, v in (out.get("mode_to_skill_id") or {}).items()}
    for mode, target in modes.items():
        if target not in seen_ids:
            errors.append(
                f"mode_to_skill_id[{mode!r}]={target!r} not found among SKILL.md names "
                f"(resolved: {sorted(seen_ids)})"
            )

    if errors:
        raise ValueError(
            f"skill bundle {root} manifest enrichment failed:\n  - " + "\n  - ".join(errors)
        )

    out["skills"] = enriched
    out["mode_to_skill_id"] = modes
    return out


def read_bundle_manifest(bundle_root: BundleRoot) -> SkillBundleManifest:
    """读取并解析 bundle（skill id 自动从各 ``SKILL.md`` 识别）。"""
    root = Path(bundle_root).resolve()
    mf = root / "manifest.json"
    if not mf.is_file():
        raise FileNotFoundError(f"missing manifest.json under {root}")
    raw = json.loads(mf.read_text(encoding="utf-8"))
    enriched = enrich_bundle_manifest(root, raw)
    entries = tuple(
        SkillBundleEntry(skill_id=str(s["id"]), path=str(s["path"]))
        for s in enriched.get("skills") or []
    )
    ids = tuple(e.skill_id for e in entries)
    return SkillBundleManifest(
        bundle_version=str(enriched.get("bundle_version", "")),
        skill_ids=ids,
        entries=entries,
        mode_to_skill_id=dict(enriched.get("mode_to_skill_id") or {}),
        root=root,
    )


def resolve_skill_bundle_root(bundle_key: str) -> Path:
    """按 ``pyproject`` entry point 名（如 ``stock-recap``）解析 bundle 根目录。"""
    try:
        eps = metadata.entry_points()
        selected = (
            eps.select(group=_ENTRY_GROUP)
            if hasattr(eps, "select")
            else eps.get(_ENTRY_GROUP, ())
        )
    except Exception as e:
        raise LookupError(f"entry_points group {_ENTRY_GROUP!r} unavailable: {e}") from e

    for ep in selected:
        if ep.name != bundle_key:
            continue
        obj = ep.load()
        out = obj() if callable(obj) else obj
        root = Path(out).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"skill bundle root is not a directory: {root} ({bundle_key})")
        return root
    raise LookupError(f"no {_ENTRY_GROUP!r} entry point named {bundle_key!r}")


def with_skill_bundle(
    defn: AgentDefinition,
    *,
    bundle_key: str,
    bundle_root: Optional[BundleRoot] = None,
) -> AgentDefinition:
    """从 bundle 自动识别的 skill id 填充 Agent 依赖字段。"""
    root = Path(bundle_root).resolve() if bundle_root is not None else resolve_skill_bundle_root(bundle_key)
    manifest = read_bundle_manifest(root)
    return replace(
        defn,
        skill_bundle=bundle_key,
        skills=list(manifest.skill_ids),
        skill_mode_map=dict(manifest.mode_to_skill_id),
    )


__all__ = [
    "SkillBundleEntry",
    "SkillBundleManifest",
    "enrich_bundle_manifest",
    "read_bundle_manifest",
    "resolve_skill_bundle_root",
    "resolve_skill_id_from_path",
    "with_skill_bundle",
]
