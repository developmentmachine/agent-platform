# 03 · Skill 资源懒加载工具

> **状态**：agent-platform 当前 `skills/<name>/` 目录下只有 `SKILL.md + manifest.json`，没有 `references / scripts / assets / templates` 子目录约定，也没有给 LLM 用的 `list_skill_files / load_skill_resource` 工具。

## 1. 背景与价值

Anthropic Skills 的核心范式：**system prompt 里只放 SKILL.md 主指令 + 资源清单（path + description），具体长文档让 agent 用工具按需 load**。

这样能：

- **省 token**：避免一次性塞光所有参考资料；
- **可治理**：资源以文件形式持久化、可审计、可热更；
- **多源统一**：本地 FS / 对象存储 / DB 用同一套 path 协议。

DataClaw 实现得很完整（包括 BOS 对象存储 + per-user 资源 + 系统资源），我们把它精简到 agent-platform 适用的形态。

## 2. DataClaw 实现摘要

源码：`/Users/zhaichuancheng/DevelopSpace/dataclaw/src/services/skills.ts`

### 2.1 资源约定

每个 skill 一个目录，固定四个子目录：

```
skills/<name>/
  SKILL.md                   # 必需，YAML frontmatter + Markdown body
  references/                # 长文档参考（默认 .md）
  scripts/                   # 代码模板（默认 .py）
  assets/                    # 静态资源（任意扩展名）
  templates/                 # 输出模板（默认 .md）
```

资源 path 协议：

- `references/<file_name>` ← 给 agent 看的 path（不带扩展名）
- 实际落盘：`<skill_dir>/references/<file_name>.<ext>`
- agent 通过 `load_skill_resource(skill, "references/foo")` 拿内容

### 2.2 列出与加载

- `listSkillResources(skill_name)` → 返回 `[{path, category, description, sort_order}]`，**第一项始终是 `SKILL.md`**（提示 agent 必要时重新加载主指令）；
- `loadSkillResource(skill_name, resource_path)` → 返回 `{resources: [{path, content}]}`，支持目录请求（如 `references/`）一次拿整组。

### 2.3 系统 vs 用户资源

`loadSkillResourceForUserOrSystem(user_id, skill, path)`：

- 若 `user_id` 提供且该用户拥有同名 user skill → 仅在用户侧查找；
- 否则查系统 skill。

**不回落**到系统同名 skill（避免越权读到系统资源）。

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  application/
    skills/
      resource_loader.py             # 资源 path 协议解析 + 加载编排
  infrastructure/
    skills/
      fs_resource_repo.py            # 本地文件系统资源仓储
      remote_resource_repo.py        # （可选）对象存储资源仓储
  infrastructure/tools/handlers/
    list_skill_files.py              # 工具实现
    load_skill_resource.py           # 工具实现
```

## 4. Python 实现骨架

### 4.1 资源协议

```python
# src/agent_platform/domain/skills.py（在 02 文档基础上扩展）
from typing import Protocol, runtime_checkable

@runtime_checkable
class SkillResourceRepository(Protocol):
    async def list_resources(
        self, skill_name: str, user_id: str | None = None
    ) -> list[SkillResource]: ...

    async def load_resource(
        self, skill_name: str, resource_path: str, user_id: str | None = None
    ) -> list[tuple[str, str]]:
        """
        返回 [(path, content), ...]。
        - 单文件请求：长度 1
        - 目录请求（"references/"）：返回整组
        """
        ...
```

### 4.2 路径协议解析

```python
# src/agent_platform/application/skills/resource_loader.py
from __future__ import annotations
import os.path

ALLOWED_CATEGORIES = ("references", "scripts", "assets", "templates")
DEFAULT_EXT_BY_CATEGORY = {
    "references": ".md",
    "scripts": ".py",
    "assets": "",          # 显式扩展
    "templates": ".md",
}


class InvalidResourcePath(ValueError):
    pass


def parse_resource_path(resource_path: str) -> tuple[str, str, bool]:
    """返回 (category, file_name, is_directory_request)。"""
    norm = resource_path.strip().rstrip("/").lower()
    if norm == "skill.md":
        return ("skill", "SKILL.md", False)
    parts = norm.split("/")
    category = parts[0]
    if category not in ALLOWED_CATEGORIES:
        raise InvalidResourcePath(
            f"Invalid resource path '{resource_path}'. Expected one of {ALLOWED_CATEGORIES}/<name>"
        )
    if len(parts) == 1:
        return (category, "", True)
    file_name = "/".join(parts[1:])
    if not file_name:
        raise InvalidResourcePath("Resource file name must not be empty.")
    return (category, file_name, False)


def implicit_extension(category: str, has_explicit_ext: bool) -> str:
    if has_explicit_ext:
        return ""
    return DEFAULT_EXT_BY_CATEGORY.get(category, "")


def has_explicit_extension(file_name: str) -> bool:
    return os.path.splitext(file_name)[1] != ""
```

### 4.3 文件系统仓储

```python
# src/agent_platform/infrastructure/skills/fs_resource_repo.py
from __future__ import annotations
import logging
from pathlib import Path

from agent_platform.application.skills.resource_loader import (
    ALLOWED_CATEGORIES,
    has_explicit_extension,
    implicit_extension,
    parse_resource_path,
)
from agent_platform.domain.skills import SkillResource

log = logging.getLogger(__name__)


class FsSkillResourceRepository:
    def __init__(self, system_skills_root: Path, user_skills_root: Path | None = None) -> None:
        self._system_root = system_skills_root
        self._user_root = user_skills_root

    def _root_for(self, user_id: str | None) -> Path:
        if user_id and self._user_root is not None:
            user_dir = self._user_root / user_id
            if user_dir.exists():
                return user_dir
        return self._system_root

    async def list_resources(
        self, skill_name: str, user_id: str | None = None
    ) -> list[SkillResource]:
        skill_dir = self._root_for(user_id) / skill_name
        if not skill_dir.exists():
            return []

        resources: list[SkillResource] = []
        # SKILL.md 始终首项
        if (skill_dir / "SKILL.md").exists():
            resources.append(
                SkillResource(
                    path="SKILL.md",
                    category="references",  # 占位
                    file_name="SKILL.md",
                    description="Main instructions file for this skill. Reload if needed.",
                    sort_order=-1,
                    file_path=str(skill_dir / "SKILL.md"),
                )
            )
        idx = 0
        for cat in ALLOWED_CATEGORIES:
            cat_dir = skill_dir / cat
            if not cat_dir.exists():
                continue
            for entry in sorted(cat_dir.iterdir(), key=lambda p: p.name):
                if not entry.is_file():
                    continue
                stem = entry.stem
                if not stem:
                    continue
                # 解析 frontmatter 抽 description（实现略，可复用 02 的 parse_frontmatter）
                desc = self._read_description(entry) or stem
                resources.append(
                    SkillResource(
                        path=f"{cat}/{stem}",
                        category=cat,  # type: ignore[arg-type]
                        file_name=stem,
                        description=desc,
                        sort_order=idx,
                        file_path=str(entry),
                    )
                )
                idx += 1
        return resources

    async def load_resource(
        self, skill_name: str, resource_path: str, user_id: str | None = None
    ) -> list[tuple[str, str]]:
        skill_dir = self._root_for(user_id) / skill_name
        if not skill_dir.exists():
            return []

        if resource_path.strip() == "SKILL.md":
            f = skill_dir / "SKILL.md"
            return [("SKILL.md", f.read_text(encoding="utf-8"))] if f.exists() else []

        category, file_name, is_dir = parse_resource_path(resource_path)
        if is_dir:
            cat_dir = skill_dir / category
            if not cat_dir.exists():
                return []
            out: list[tuple[str, str]] = []
            for entry in sorted(cat_dir.iterdir(), key=lambda p: p.name):
                if entry.is_file():
                    out.append((f"{category}/{entry.stem}", entry.read_text(encoding="utf-8")))
            return out

        ext = implicit_extension(category, has_explicit_extension(file_name))
        target = skill_dir / category / f"{file_name}{ext}"
        if not target.exists():
            log.warning("[skill-resource] not found: %s", target)
            return []
        return [(f"{category}/{file_name}", target.read_text(encoding="utf-8"))]

    @staticmethod
    def _read_description(path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
            if text.startswith("---"):
                _, fm, _ = text.split("---", 2)
                for line in fm.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        if k.strip().lower() == "description":
                            return v.strip().strip('"\'')
        except Exception:
            log.warning("[skill-resource] read description failed: %s", path, exc_info=True)
        return ""
```

### 4.4 工具实现（agent-platform 现有 tools/handlers 风格）

```python
# src/agent_platform/infrastructure/tools/handlers/list_skill_files.py
from __future__ import annotations
import json

from agent_platform.domain.skills import SkillResourceRepository

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_skill_files",
        "description": (
            "List the resource files for a skill (references/scripts/assets/templates). "
            "SKILL.md is always returned as the first item. Use load_skill_resource to read content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Activated skill name."},
            },
            "required": ["skill_name"],
        },
    },
}


class ListSkillFilesHandler:
    name = "list_skill_files"

    def __init__(self, repo: SkillResourceRepository) -> None:
        self._repo = repo

    async def __call__(self, args: dict, ctx) -> str:
        skill_name = (args.get("skill_name") or "").strip().lower()
        if not skill_name:
            return json.dumps({"success": False, "error": "skill_name is required"})
        resources = await self._repo.list_resources(skill_name, user_id=ctx.principal_id)
        return json.dumps(
            {
                "success": True,
                "skill_name": skill_name,
                "resources": [
                    {
                        "path": r.path,
                        "category": r.category,
                        "description": r.description,
                        "sort_order": r.sort_order,
                    }
                    for r in resources
                ],
            },
            ensure_ascii=False,
        )
```

```python
# src/agent_platform/infrastructure/tools/handlers/load_skill_resource.py
from __future__ import annotations
import json

from agent_platform.application.skills.resource_loader import InvalidResourcePath
from agent_platform.domain.skills import SkillResourceRepository

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "load_skill_resource",
        "description": (
            "Load one resource file (or all files in a category like 'references/') for a skill. "
            "Path format: 'references/foo' / 'scripts/bar' / 'assets/img1.png' / 'SKILL.md' / 'references/'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string"},
                "resource_path": {"type": "string"},
            },
            "required": ["skill_name", "resource_path"],
        },
    },
}


class LoadSkillResourceHandler:
    name = "load_skill_resource"

    def __init__(self, repo: SkillResourceRepository) -> None:
        self._repo = repo

    async def __call__(self, args: dict, ctx) -> str:
        skill_name = (args.get("skill_name") or "").strip().lower()
        path = (args.get("resource_path") or "").strip()
        if not skill_name or not path:
            return json.dumps(
                {"success": False, "error": "skill_name and resource_path are required"}
            )
        try:
            pairs = await self._repo.load_resource(skill_name, path, user_id=ctx.principal_id)
        except InvalidResourcePath as e:
            return json.dumps({"success": False, "error": str(e)})
        if not pairs:
            return json.dumps({"success": False, "error": f"resource not found: {path}"})
        return json.dumps(
            {
                "success": True,
                "skill_name": skill_name,
                "resources": [{"path": p, "content": c} for p, c in pairs],
            },
            ensure_ascii=False,
        )
```

### 4.5 注册到 tools registry

```python
# 在 infrastructure/tools/registry.py 启动注册时添加：
registry.register(ListSkillFilesHandler(skill_resource_repo))
registry.register(LoadSkillResourceHandler(skill_resource_repo))
```

## 5. 与 02 SOUL 装配的协同

`SoulComposer.compose()` 渲染激活 skill 时，会在 `Available resources` 段列出 `path + description`，**LLM 看到清单后自行决定调用 `load_skill_resource`**——这就是懒加载范式生效的方式。

## 6. 配置

`.env.example` 增量：

```bash
SKILL_SYSTEM_ROOT=./src/agent_platform/skills
SKILL_USER_ROOT=./var/user-skills           # 可选，启用 per-user
```

## 7. 迁移步骤

1. **PR-1（约定）**：现有 skills 加 `references/scripts/assets/templates` 子目录（即使空也保留 `.gitkeep`），并在 `manifest.json` 的 `description` 之外增加 frontmatter 风格的 `SKILL.md`。
2. **PR-2（resource repo）**：实现 `FsSkillResourceRepository`，单测覆盖 happy path / 无目录 / 无文件 / 目录请求 / 路径越界。
3. **PR-3（工具）**：注册 `list_skill_files` / `load_skill_resource`，在已有 stock-recap agent 上跑一次 turn 验证 LLM 调用链。
4. **PR-4（per-user）**：接入 user_id（详见 `05-per-user-tenancy.md`）。

## 8. 验收标准

- [ ] `list_skill_files` 第一项必为 `SKILL.md`；
- [ ] `load_skill_resource("a_share_daily_recap", "references/foo")` 不带扩展名也能命中 `.md`；
- [ ] 加载 `references/` 目录返回多文件；
- [ ] 未知 path 返回 `success=false` 而不是抛异常；
- [ ] user skill 存在同名时只读用户侧、不回落到系统侧（多租户隔离）。

## 9. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `src/services/skills.ts::listSkillResources` | `FsSkillResourceRepository.list_resources` |
| `src/services/skills.ts::loadSkillResource` | `FsSkillResourceRepository.load_resource` |
| `src/services/skills.ts::skillResourceRelativePathSegments` | `application/skills/resource_loader.py::parse_resource_path` |
| `src/services/skills.ts::skillResourceImplicitExt` | `application/skills/resource_loader.py::implicit_extension` |
| dataclaw 工具 `list_skill_files` / `load_skill_resource` | `infrastructure/tools/handlers/{list_skill_files,load_skill_resource}.py` |
