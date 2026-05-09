# 06 · 命令权限四态机

> **状态**：agent-platform 已有 `policy/guardrails.py` + `policy/rules.yaml`，思路对路；但缺少"运行时审批 + 持久化批准 + 前缀通配"这一层。一旦 agent 能跑 shell / SQL / 写文件，就必须有这个机制。

## 1. 背景

任何能让 LLM 执行外部副作用的工具（`run_command` / `execute_sql` / `web_request` / `write_file`）都需要一道权限门：

- **safe**：白名单命令（`ls`, `cat`, `git status` ...），直接放行；
- **dangerous**：高风险正则（`rm -rf` / `sudo` / `curl ... | sh` / fork bomb），强制需审批；
- **denied**：用户/管理员明确拒绝过的命令；
- **approved**：用户/管理员明确允许过的命令（支持 `xxx*` 前缀通配）；
- **needs_approval**：以上都不命中时的默认值——返回审批请求给上游。

DataClaw 把它做成 4 态枚举 + 双后端（本地 JSON / DB）+ 前缀规则，是一套很完整的工程化方案。

## 2. DataClaw 实现拆解

源码：`/Users/zhaichuancheng/DevelopSpace/dataclaw/src/stores/permissions.ts`

```ts
export type CommandSafety = 'safe' | 'approved' | 'needs_approval' | 'denied';

const SAFE_COMMANDS = new Set(['ls','cat','head','tail','wc','date','whoami','echo','pwd','which','git','node','pnpm','uv']);

const DANGEROUS_PATTERNS = [
  /\brm\b/i, /\bsudo\b/i, /\bchmod\b/i, /\bchown\b/i,
  /\bdd\b/i, /\bmkfs\b/i,
  /curl\s+[^|]*\|\s*(sh|bash|zsh)/i,
  /:\(\)\s*\{\s*:\|:&\s*\};:/,                      // fork bomb
];
```

判定顺序：

```
SAFE 白名单 → DANGEROUS 正则强制审批 → denied 列表 → allowed 列表 → 默认 needs_approval
```

前缀规则：`git push *` 之类，匹配 `git push origin main` / `git push --force` 等。

后端：`LocalFileApprovalsBackend`（JSON 文件）/ `PrismaApprovalsBackend`（DB），通过 `PermissionManager` 抽象统一接口。

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  policy/
    guardrails.py                     # 已有，扩展 CommandSafetyEvaluator
    rules.yaml                        # 已有，新增 safe/dangerous/allowed/denied 字段
    permission_manager.py             # 新增：状态机 + 前缀匹配
  domain/
    permissions.py                    # 协议 + 数据类
  infrastructure/
    permissions/
      sql_repository.py               # DB 后端
      file_repository.py              # 本地 JSON 后端
  interfaces/api/v1/admin/
    permissions.py                    # CRUD allowed/denied
```

## 4. Python 实现骨架

### 4.1 领域

```python
# src/agent_platform/domain/permissions.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class CommandSafety(str, Enum):
    SAFE = "safe"
    APPROVED = "approved"
    NEEDS_APPROVAL = "needs_approval"
    DENIED = "denied"


@dataclass(frozen=True)
class ApprovalsStore:
    allowed: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()


@runtime_checkable
class ApprovalsRepository(Protocol):
    async def load(self, key: str = "global") -> ApprovalsStore: ...
    async def save(self, store: ApprovalsStore, key: str = "global") -> None: ...
```

### 4.2 状态机

```python
# src/agent_platform/policy/permission_manager.py
from __future__ import annotations
import re
from dataclasses import dataclass, field

from agent_platform.domain.permissions import (
    ApprovalsRepository,
    ApprovalsStore,
    CommandSafety,
)

DEFAULT_SAFE_COMMANDS = frozenset(
    "ls cat head tail wc date whoami echo pwd which git node uv python python3 pip uvx".split()
)
DEFAULT_DANGEROUS_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\brm\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bchmod\b", re.IGNORECASE),
    re.compile(r"\bchown\b", re.IGNORECASE),
    re.compile(r"\bdd\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"curl\s+[^|]*\|\s*(sh|bash|zsh)", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),                        # fork bomb
    re.compile(r"\bdrop\s+(database|schema|table)\b", re.IGNORECASE),# 给 SQL 用
)


def _normalize(command: str) -> str:
    return " ".join(command.strip().split())


def _match_prefix_rule(command: str, rule: str) -> bool:
    if not rule.endswith("*"):
        return False
    prefix = rule[:-1].rstrip()
    return command == prefix or command.startswith(prefix + " ")


@dataclass
class PermissionManager:
    repo: ApprovalsRepository
    safe_commands: frozenset[str] = DEFAULT_SAFE_COMMANDS
    dangerous_patterns: tuple[re.Pattern, ...] = DEFAULT_DANGEROUS_PATTERNS

    async def check(self, command: str, key: str = "global") -> CommandSafety:
        normalized = _normalize(command)
        if not normalized:
            return CommandSafety.NEEDS_APPROVAL

        base = normalized.split(" ", 1)[0]
        if base in self.safe_commands:
            return CommandSafety.SAFE

        if any(p.search(normalized) for p in self.dangerous_patterns):
            return CommandSafety.NEEDS_APPROVAL  # 即便已 approved，危险命令也再次确认

        store = await self.repo.load(key)
        if any(_exact_or_prefix(normalized, rule) for rule in store.denied):
            return CommandSafety.DENIED
        if any(_exact_or_prefix(normalized, rule) for rule in store.allowed):
            return CommandSafety.APPROVED

        return CommandSafety.NEEDS_APPROVAL

    async def save_approval(
        self, command: str, approved: bool, key: str = "global"
    ) -> None:
        normalized = _normalize(command)
        store = await self.repo.load(key)
        bucket = "allowed" if approved else "denied"
        current = list(getattr(store, bucket))
        if normalized not in current:
            current.append(normalized)
        new_store = ApprovalsStore(
            allowed=tuple(store.allowed) if approved is False else tuple(current),
            denied=tuple(current) if approved is False else tuple(store.denied),
        )
        await self.repo.save(new_store, key)


def _exact_or_prefix(command: str, rule: str) -> bool:
    return command == rule or _match_prefix_rule(command, rule)
```

> **注意**：dataclaw 在"危险命令"命中时无视 allowed 列表强制审批，我们沿用这个保守策略，避免误把 `rm -rf` 加入 allowed 后无人审批就执行。

### 4.3 文件后端 + DB 后端

```python
# src/agent_platform/infrastructure/permissions/file_repository.py
import json
from pathlib import Path

from agent_platform.domain.permissions import ApprovalsRepository, ApprovalsStore

class FileApprovalsRepository(ApprovalsRepository):
    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self, key: str = "global") -> ApprovalsStore:
        if not self._path.exists():
            return ApprovalsStore()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return ApprovalsStore(
                allowed=tuple(data.get("allowed", [])),
                denied=tuple(data.get("denied", [])),
            )
        except Exception:
            return ApprovalsStore()

    async def save(self, store: ApprovalsStore, key: str = "global") -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"allowed": list(store.allowed), "denied": list(store.denied)}, indent=2),
            encoding="utf-8",
        )
```

```python
# src/agent_platform/infrastructure/permissions/sql_repository.py
from agent_platform.domain.permissions import ApprovalsRepository, ApprovalsStore
from agent_platform.infrastructure.persistence.models import CommandApprovalRow

class SqlApprovalsRepository(ApprovalsRepository):
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def load(self, key: str = "global") -> ApprovalsStore:
        async with self._session_factory() as session:
            row = (await session.execute(
                select(CommandApprovalRow).where(CommandApprovalRow.approval_key == key)
            )).scalar_one_or_none()
            if row is None:
                return ApprovalsStore()
            return ApprovalsStore(
                allowed=tuple(row.allowed or []),
                denied=tuple(row.denied or []),
            )

    async def save(self, store: ApprovalsStore, key: str = "global") -> None:
        async with self._session_factory() as session, session.begin():
            row = (await session.execute(
                select(CommandApprovalRow).where(CommandApprovalRow.approval_key == key)
            )).scalar_one_or_none()
            if row is None:
                row = CommandApprovalRow(approval_key=key)
                session.add(row)
            row.allowed = list(store.allowed)
            row.denied  = list(store.denied)
```

## 5. 接入 tool runner

```python
# src/agent_platform/infrastructure/tools/handlers/run_command.py
from agent_platform.domain.permissions import CommandSafety
from agent_platform.policy.permission_manager import PermissionManager

class RunCommandHandler:
    name = "run_command"

    def __init__(self, manager: PermissionManager, executor) -> None:
        self._manager = manager
        self._executor = executor

    async def __call__(self, args: dict, ctx) -> str:
        cmd = (args.get("command") or "").strip()
        if not cmd:
            return json.dumps({"success": False, "error": "command is required"})
        safety = await self._manager.check(cmd, key=ctx.principal_id or "global")

        if safety is CommandSafety.DENIED:
            return json.dumps(
                {"success": False, "safety": "denied", "error": f"command denied: {cmd!r}"}
            )
        if safety is CommandSafety.NEEDS_APPROVAL:
            return json.dumps(
                {
                    "success": False,
                    "safety": "needs_approval",
                    "approval_request": {
                        "command": cmd,
                        "approval_url": f"/v1/admin/permissions/{ctx.principal_id}/approve?cmd={cmd}",
                    },
                    "error": "command needs human approval before execution",
                }
            )

        # safe / approved
        result = await self._executor.run(cmd, timeout_s=ctx.command_timeout_s)
        return json.dumps({"success": result.exit_code == 0, "safety": safety.value, **result.dict()})
```

> **重要**：`needs_approval` 不抛异常，而是把审批请求作为 tool 输出回给 LLM；LLM 看到后会停下并向用户传达审批链接。这与 dataclaw 的体感一致：agent 是"非阻塞"的。

## 6. Admin API

```python
# src/agent_platform/interfaces/api/v1/admin/permissions.py
@router.get("/permissions/{key}")
async def list_approvals(key: str = "global", deps=Depends(...)):
    store = await deps.approvals_repo.load(key)
    return {"allowed": list(store.allowed), "denied": list(store.denied)}

@router.post("/permissions/{key}/approve")
async def approve(key: str, body: ApprovalReq, deps=Depends(...)):
    await deps.permission_manager.save_approval(body.command, approved=True, key=key)
    return {"ok": True}

@router.post("/permissions/{key}/deny")
async def deny(key: str, body: ApprovalReq, deps=Depends(...)):
    await deps.permission_manager.save_approval(body.command, approved=False, key=key)
    return {"ok": True}
```

## 7. 配置 `policy/rules.yaml` 扩展

```yaml
commands:
  safe:
    - ls
    - cat
    - head
    - tail
    - git
    - python
    - python3
    - uv
    - uvx
  dangerous_patterns:
    - "\\brm\\b"
    - "\\bsudo\\b"
    - "curl\\s+[^|]*\\|\\s*(sh|bash|zsh)"
  preset_allowed:
    - "git status"
    - "git log*"
    - "ls -la*"
  preset_denied:
    - "rm -rf /"
```

`PermissionManager` 启动时把 `preset_allowed/denied` 与 repo 加载到的合并。

## 8. 迁移步骤

1. **PR-1**：domain 协议 + state machine 实现 + 单测（覆盖 4 态 × 各种命令）。
2. **PR-2**：File / SQL 后端 + DB migration（`command_approvals` 表）。
3. **PR-3**：`run_command` / `execute_sql` 等 handler 接入；现有 guardrails.py 重构为薄壳调用 PermissionManager。
4. **PR-4**：admin API + 文档；运营手册说明审批流程。

## 9. 验收标准

- [ ] `ls -la` → safe；
- [ ] `git status` 不在 SAFE 单词，但 `git` 在 → safe；
- [ ] `rm -rf node_modules` → needs_approval（即使已加入 allowed 也仍审批）；
- [ ] `git push origin main` 命中 `git push*` → approved；
- [ ] 无任何规则命中 → needs_approval（默认值）；
- [ ] 工具返回结构包含 `safety / approval_request`，agent loop 能优雅停下。

## 10. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `src/stores/permissions.ts::CommandSafety` | `domain/permissions.py::CommandSafety` |
| `src/stores/permissions.ts::SAFE_COMMANDS / DANGEROUS_PATTERNS` | `policy/permission_manager.py` 顶层常量 + `rules.yaml` |
| `src/stores/permissions.ts::PermissionManager` | `policy/permission_manager.py::PermissionManager` |
| `src/stores/permissions.ts::LocalFileApprovalsBackend` | `infrastructure/permissions/file_repository.py` |
| `src/stores/permissions.ts::PrismaApprovalsBackend` | `infrastructure/permissions/sql_repository.py` |
| `prisma/schema.prisma::CommandApproval` | `command_approvals` 表 + `CommandApprovalRow` |
