# 05 · 多租户：per-user MCP / per-user Skill

> **状态**：agent-platform 已有 `domain/principal.py` 这个用户上下文，但 `tools/registry.py`、`skills/loader.py` 都是**全局单例**，没有 per-user 维度。本专题补齐"每个用户挂自己的工具/技能"能力。

## 1. 背景

B2B SaaS / B2C 平台的 agent 几乎一定要支持：

- **每个用户接自己的 MCP server**（自己的数据库、自己的 Notion、自己的内部 API）；
- **每个用户上传自己的 Skill**（自己的提示词库 / 自己的工作流模板）；
- **系统级资产对所有人可见，且不可被用户同名覆盖**（防越权与污染）。

DataClaw 的实现：

- 系统资产从配置文件 / DB 加载，标 `source: "system"`；
- 用户资产存储在 DB（`user_mcp_servers` 表）/ 对象存储（BOS 的 `userSkillPrefix/<user_id>/...` 前缀）；
- 合并时**系统优先**，用户同名直接 `console.warn` 跳过；
- agent loop 取工具/技能时透传 `user_id`，registry 内部按可见性 + 合并逻辑算出该用户能用的集合。

## 2. DataClaw 实现要点

### 2.1 user MCP

`prisma/schema.prisma` 的 `UserMcpServer` 表：

```prisma
model UserMcpServer {
  id        BigInt   @id @default(autoincrement())
  userId    String   @default("")
  serverKey String   @default("")
  isPublic  Boolean  @default(false)
  agentIds  Json?              // 非公开时白名单
  transport Json?              // stdio/sse/http 配置
  enabled   Boolean  @default(true)
  @@unique([userId, serverKey])
}
```

`mcpRegistry.mergeForUser`：

```ts
private mergeForUser(userRows: McpServerDefinition[]): McpServerDefinition[] {
  const map = new Map<string, McpServerDefinition>();
  for (const s of this.systemServers) map.set(s.serverKey, s);
  for (const u of userRows) {
    if (map.has(u.serverKey)) {
      console.warn(`[mcp] skipping user MCP "${u.serverKey}" (conflicts with system)`);
      continue;
    }
    map.set(u.serverKey, u);
  }
  return [...map.values()];
}
```

### 2.2 user Skill

DataClaw 把用户 skill 存在对象存储：`{userSkillPrefix}/<user_id>/<skill_name>/SKILL.md` + `{references,scripts,assets,templates}/...`。

`mergeUserSkills`：

```ts
private async mergeUserSkills(userId?: string): Promise<SkillDefinition[]> {
  if (!userId || !this.bosConfig) return this.skills;
  const userSkills = await this.discoverUserSkills(userId);
  const publicNames = new Set(this.skills.map((s) => s.name));
  const extra = userSkills.filter((s) => !publicNames.has(s.name));
  return [...this.skills, ...extra];
}
```

注意：**用户同名 skill 被丢弃**，不会覆盖系统 skill。这是关键安全策略。

### 2.3 资源加载的"用户优先 + 不回落"

`loadSkillResourceForUserOrSystem(user_id, skill, path)`：

- 若 `user_id` 提供且该用户拥有同名 user skill → 仅在用户侧查找；
- 否则查系统 skill。

**user skill 命中后不回落到系统**，避免越权读到系统资源。

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  domain/
    mcp.py                           # 已在 01 文档定义 UserMcpRepository
    skills.py                        # 在 02 文档基础上扩展 user 相关 API
  infrastructure/
    persistence/
      models.py                      # SQLAlchemy 模型
      repositories.py
        - SqlUserMcpRepository       # user_mcp_servers
        - SqlUserSkillRepository     # user_skills_meta + 文件/对象存储
    skills/
      remote_resource_repo.py        # 对象存储版资源仓储（可选）
  interfaces/api/v1/admin/
    mcp.py                           # CRUD user MCP（已在 01 提到）
    skills.py                        # CRUD user skill
```

## 4. 数据模型

### 4.1 SQL 表（PostgreSQL/MySQL 通用）

```sql
-- user_mcp_servers
CREATE TABLE user_mcp_servers (
  id           BIGSERIAL PRIMARY KEY,
  user_id      VARCHAR(255) NOT NULL DEFAULT '',
  server_key   VARCHAR(64)  NOT NULL DEFAULT '',
  is_public    BOOLEAN      NOT NULL DEFAULT FALSE,
  agent_ids    JSONB,
  transport    JSONB,
  enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (user_id, server_key)
);
CREATE INDEX idx_user_mcp_user_id ON user_mcp_servers(user_id);

-- user_skills_meta（实际 SKILL.md 与 resources 落对象存储/本地 FS）
CREATE TABLE user_skills_meta (
  id           BIGSERIAL PRIMARY KEY,
  user_id      VARCHAR(255) NOT NULL,
  skill_name   VARCHAR(64)  NOT NULL,
  description  VARCHAR(1024) NOT NULL DEFAULT '',
  enabled      BOOLEAN      NOT NULL DEFAULT TRUE,
  storage_uri  VARCHAR(512) NOT NULL,    -- e.g. s3://bucket/user-skills/<uid>/<name>/
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (user_id, skill_name)
);
```

### 4.2 SQLAlchemy 模型（节选）

```python
# src/agent_platform/infrastructure/persistence/models.py
from sqlalchemy import Column, BigInteger, String, Boolean, JSON, DateTime, UniqueConstraint, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class UserMcpServerRow(Base):
    __tablename__ = "user_mcp_servers"
    id          = Column(BigInteger, primary_key=True)
    user_id     = Column(String(255), nullable=False, default="")
    server_key  = Column(String(64), nullable=False, default="")
    is_public   = Column(Boolean, nullable=False, default=False)
    agent_ids   = Column(JSON, nullable=True)
    transport   = Column(JSON, nullable=True)
    enabled     = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("user_id", "server_key"),)
```

## 5. 仓储实现骨架

```python
# src/agent_platform/infrastructure/persistence/repositories.py
from agent_platform.domain.mcp import McpServerDefinition, UserMcpRepository

class SqlUserMcpRepository(UserMcpRepository):
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def list_by_user_id(self, user_id: str) -> list[McpServerDefinition]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(UserMcpServerRow).where(UserMcpServerRow.user_id == user_id, UserMcpServerRow.enabled.is_(True))
            )).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def upsert(self, user_id: str, defn: McpServerDefinition) -> None:
        async with self._session_factory() as session, session.begin():
            row = (await session.execute(
                select(UserMcpServerRow).where(
                    UserMcpServerRow.user_id == user_id,
                    UserMcpServerRow.server_key == defn.server_key,
                )
            )).scalar_one_or_none()
            if row is None:
                row = UserMcpServerRow(user_id=user_id, server_key=defn.server_key)
                session.add(row)
            row.is_public = defn.is_public
            row.agent_ids = list(defn.agent_ids)
            row.transport = defn.transport
            row.enabled   = defn.enabled

    async def delete(self, user_id: str, server_key: str) -> bool:
        async with self._session_factory() as session, session.begin():
            res = await session.execute(
                delete(UserMcpServerRow).where(
                    UserMcpServerRow.user_id == user_id,
                    UserMcpServerRow.server_key == server_key,
                )
            )
            return (res.rowcount or 0) > 0

    @staticmethod
    def _to_domain(r: UserMcpServerRow) -> McpServerDefinition:
        return McpServerDefinition(
            server_key=r.server_key,
            source="user",
            enabled=bool(r.enabled),
            is_public=bool(r.is_public),
            agent_ids=tuple(r.agent_ids or []),
            transport=r.transport or {},
        )
```

## 6. Admin API

```python
# src/agent_platform/interfaces/api/v1/admin/mcp.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/admin/mcp", tags=["admin-mcp"])

class UpsertUserMcpReq(BaseModel):
    server_key: str
    is_public: bool = False
    agent_ids: list[str] = []
    transport: dict
    enabled: bool = True

@router.get("/users/{user_id}")
async def list_user_mcp(user_id: str, deps=Depends(...)):
    return await deps.mcp_registry.list_catalog_for_display(user_id)

@router.put("/users/{user_id}/{server_key}")
async def upsert_user_mcp(user_id: str, server_key: str, body: UpsertUserMcpReq, deps=Depends(...)):
    if server_key in deps.mcp_registry.system_server_keys():
        raise HTTPException(409, f"server_key {server_key!r} conflicts with system")
    defn = McpServerDefinition(
        server_key=server_key, source="user",
        enabled=body.enabled, is_public=body.is_public,
        agent_ids=tuple(body.agent_ids), transport=body.transport,
    )
    await deps.user_mcp_repo.upsert(user_id, defn)
    await deps.mcp_pool.evict_user_server(user_id, server_key)
    return {"ok": True}

@router.delete("/users/{user_id}/{server_key}")
async def delete_user_mcp(user_id: str, server_key: str, deps=Depends(...)):
    ok = await deps.user_mcp_repo.delete(user_id, server_key)
    if ok:
        await deps.mcp_pool.evict_user_server(user_id, server_key)
    return {"ok": ok}
```

`/admin/skills/users/{user_id}` 同理，参考 dataclaw `routes/skills.ts`：list / get / upsert / delete / list_resources / upsert_resource / load_resource。

## 7. 工具调度透传 user_id

agent-platform 现有 `infrastructure/tools/runner.py` 在执行 tool call 时，必须把 `principal.id` 当 `user_id` 传给：

- `mcp_registry.execute_mcp_tool(agent_id, user_id, pool, ...)`
- `skill_router.route(user_text, user_id)`
- `skill_resource_repo.list_resources(skill, user_id)`

## 8. 鉴权与防越权

| 资源 | 操作 | 谁能做 |
|---|---|---|
| 系统 MCP | 读 / 写 / 删 | 仅平台 admin（独立 admin token） |
| 用户 MCP | 读 / 写 / 删（自己的） | 用户本人 |
| 用户 MCP（别人的） | - | 永远禁止 |
| 系统 Skill | 读 | 所有人 |
| 系统 Skill | 写 / 删 | 仅平台 admin（且 `skill_type=builtin` 的不允许改/删） |
| 用户 Skill | CRUD（自己的） | 用户本人 |

中间件示例：

```python
async def require_admin(token: str = Depends(oauth2_scheme)) -> Principal:
    principal = await auth.verify(token)
    if not principal.is_platform_admin:
        raise HTTPException(403, "admin only")
    return principal
```

## 9. 配置

`.env.example` 增量：

```bash
USER_SKILLS_STORAGE=local                   # local | s3 | bos
USER_SKILLS_LOCAL_ROOT=./var/user-skills
# 若用 S3：
USER_SKILLS_S3_BUCKET=
USER_SKILLS_S3_PREFIX=user-skills
```

## 10. 迁移步骤

1. **PR-1**：DB 迁移（`user_mcp_servers` / `user_skills_meta`），`SqlUserMcpRepository` 实现 + 单测。
2. **PR-2**：（依赖 01 MCP 完成）`McpRegistry` 接入 `SqlUserMcpRepository`，admin API CRUD + 触发 evict。
3. **PR-3**：（依赖 02/03 Skill 完成）`SkillRouter._merge_user_skills` 加用户 skill 合并；`SkillResourceRepository` 增加 user 维度。
4. **PR-4**：admin/skills CRUD（含 user 资源上传/下载）。

## 11. 验收标准

- [ ] 用户 A 配置自己的 MCP `notion`，下次 turn 立即出现在 tool 列表里；
- [ ] 用户 B 看不到用户 A 的 `notion`；
- [ ] 用户尝试上传同名系统 MCP `filesystem` → 被 admin API 拒绝（409）；
- [ ] 用户上传同名 skill → router 不会激活用户版（系统优先）；
- [ ] `load_skill_resource` 在用户拥有同名 skill 时**只读用户侧**，不回落系统侧。

## 12. 对照源码

| dataclaw 位置 | agent-platform 目标 |
|---|---|
| `prisma/schema.prisma::UserMcpServer` | SQL 表 `user_mcp_servers` + SQLAlchemy `UserMcpServerRow` |
| `src/stores/userMcpStore.ts` | `infrastructure/persistence/repositories.py::SqlUserMcpRepository` |
| `src/services/mcp/mcpRegistry.ts::mergeForUser` | `infrastructure/mcp/registry.py::_merge_for_user` |
| `src/services/skills.ts::discoverUserSkills / mergeUserSkills` | `application/skills/router.py` 中 `route()` 合并逻辑 |
| `src/services/skills.ts::loadSkillResourceForUserOrSystem` | `infrastructure/skills/fs_resource_repo.py::load_resource(user_id=...)` |
| `src/routes/skills.ts` | `interfaces/api/v1/admin/{mcp,skills}.py` |
