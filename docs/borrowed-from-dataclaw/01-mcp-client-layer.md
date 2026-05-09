# 01 · MCP Client 接入层

> **状态**：agent-platform 当前**完全缺失**。`infrastructure/` 下没有 MCP client 模块，只有 `interfaces/mcp_stdio.py` 把自身暴露为 MCP server。这是优先级最高的借鉴项。

## 1. 背景与价值

MCP（Model Context Protocol）是 Anthropic 主推的"工具协议总线"。一个生产级 agent 通常需要：

- 同时连接多个 MCP server（数据库、Jira、内部 API、文件系统、…）；
- 支持多种 transport（stdio / SSE / HTTP）；
- 每个用户能挂自己的 MCP server（多租户）；
- 把 MCP tool 转换成 LLM Provider（OpenAI/Anthropic）的 function-calling 描述；
- 连接复用 + 超时控制 + 失败隔离 + 配置脱敏。

DataClaw 在 `src/services/mcp/` 沉淀了一套**生产可用**的 MCP client 模块。我们把它 Python 化引入 `agent-platform`。

## 2. DataClaw 实现拆解

源码：`/Users/zhaichuancheng/DevelopSpace/dataclaw/src/services/mcp/`

```
mcp/
  envSubstitute.ts            # 配置中 ${ENV_VAR} 插值
  loadSystemMcpFile.ts        # 启动期加载系统级 MCP 配置文件
  mcpRegistry.ts              # 系统/用户 MCP 合并 + 可见性过滤
  mcpSessionPool.ts           # scopeUserId::serverKey 池化 + in-flight 去重
  naming.ts                   # MCP tool name → OpenAI function name
  parseConfig.ts              # 配置反序列化 + 校验
  redactTransportForDisplay.ts# 展示前对 API key/headers 脱敏
  transportFactory.ts         # stdio / SSE / HTTP 多 transport 构造
  types.ts                    # 配置 / 协议 类型
```

### 2.1 关键模型（`types.ts` 等价）

```ts
interface McpServerDefinition {
  serverKey: string;                  // 全局唯一键，如 "datalake_mysql"
  source: 'system' | 'user';
  enabled: boolean;
  isPublic: boolean;                  // true: 所有 agent 可见
  agentIds: string[];                 // isPublic=false 时白名单
  transport: McpTransportConfig;      // stdio / sse / http
}
```

### 2.2 注册中心（`mcpRegistry.ts`）

- `mergeForUser(userRows)`：系统优先；用户同名 `console.warn` 跳过；
- `visibleDefinitions(agentId, userId)`：按 `enabled / isPublic / agentIds` 过滤；
- `buildOpenAiTools(agentId, userId, pool)`：聚合所有可见 server 的 tools 拼成 LLM 工具列表；
- `executeMcpTool(...)`：在所有可见 server 中查找该 function name 并执行；
- `listCatalogForDisplay(userId)`：返回脱敏后的目录给管理端 API。

### 2.3 会话池（`mcpSessionPool.ts`）

- 池 key = `${scopeUserId}::${serverKey}`，系统 server 用 `__system__` 共享；
- `inFlight: Map<key, Promise>` 去重并发连接；
- 每个 session 持有 `client + openAiTools[] + openAiToNative` 映射；
- `serializeMcpToolResult(result)`：把 MCP 标准返回（`isError` / `content[].text` / `structuredContent`）归一化成 LLM 友好的字符串；
- `evictUserServer(userId, serverKey)` 用于用户更新配置后强制重连；
- `closeAll()` 优雅关闭。

### 2.4 工具命名（`naming.ts`）

`buildMcpOpenAiFunctionName(serverKey, nativeName)` → `mcp__<serverKey>__<nativeName>`，且 `mcpSessionPool` 在重名时自动加 `_2`、`_3` 后缀。

## 3. 在 agent-platform 的目标位置

```
src/agent_platform/
  domain/
    mcp.py                            # 协议 + 模型（MCP 视角的纯领域）
  application/
    mcp/
      __init__.py
      tool_aggregator.py              # 聚合可见 server 的 tools 给 application 用
  infrastructure/
    mcp/
      __init__.py
      types.py                        # McpServerDefinition / McpTransportConfig (pydantic)
      env_substitute.py               # ${VAR} 插值
      parse_config.py                 # 反序列化 + 校验
      transport_factory.py            # stdio / sse / http
      naming.py                       # tool name 映射
      session_pool.py                 # asyncio 版会话池
      registry.py                     # 系统/用户合并 + 可见性
      redact.py                       # 脱敏
      load_system_file.py             # 加载系统 MCP yaml
  interfaces/
    api/v1/admin/mcp.py               # 管理端 CRUD
```

`domain/mcp.py` 只放协议（接口）和值对象，**不依赖任何具体 SDK**：

```python
# src/agent_platform/domain/mcp.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class McpServerDefinition:
    server_key: str
    source: str                         # "system" | "user"
    enabled: bool
    is_public: bool
    agent_ids: tuple[str, ...]
    transport: dict                     # 不强约束，由 infrastructure 解释

@runtime_checkable
class UserMcpRepository(Protocol):
    async def list_by_user_id(self, user_id: str) -> list[McpServerDefinition]: ...
    async def upsert(self, user_id: str, server: McpServerDefinition) -> None: ...
    async def delete(self, user_id: str, server_key: str) -> bool: ...
```

## 4. Python 实现骨架

> 完整实现交给执行 session 写。这里给出**关键骨架**，包含全部边界处理与 dataclaw 同语义。

### 4.1 会话池

```python
# src/agent_platform/infrastructure/mcp/session_pool.py
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from mcp import ClientSession                # python mcp sdk
from mcp.types import Tool as McpTool

from agent_platform.observability import metrics
from .naming import build_openai_function_name
from .transport_factory import open_transport
from .types import McpServerDefinition

log = logging.getLogger(__name__)

@dataclass
class PooledMcpSession:
    open_ai_tools: list[dict]                       # 直接可塞给 LLM API
    call_tool: Callable[[str, dict], Awaitable[str]]
    close: Callable[[], Awaitable[None]]


class McpSessionPool:
    def __init__(self, tool_timeout_ms: int) -> None:
        self._timeout_s = tool_timeout_ms / 1000
        self._sessions: dict[str, PooledMcpSession] = {}
        self._inflight: dict[str, asyncio.Task[PooledMcpSession | None]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(scope_user_id: str, server_key: str) -> str:
        return f"{scope_user_id}::{server_key}"

    async def get_session(
        self, defn: McpServerDefinition, scope_user_id: str
    ) -> PooledMcpSession | None:
        key = self._key(scope_user_id, defn.server_key)
        if (existing := self._sessions.get(key)) is not None:
            return existing

        async with self._lock:
            if (existing := self._sessions.get(key)) is not None:
                return existing
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._connect_one(defn, key))
                self._inflight[key] = task

        try:
            return await task
        finally:
            self._inflight.pop(key, None)

    async def _connect_one(
        self, defn: McpServerDefinition, key: str
    ) -> PooledMcpSession | None:
        try:
            transport_ctx = open_transport(defn.transport)
            client = await transport_ctx.__aenter__()
            await client.initialize()
            mcp_tools = await client.list_tools()

            used_names: set[str] = set()
            openai_to_native: dict[str, str] = {}
            tools: list[dict] = []
            for t in mcp_tools.tools:
                openai_name = self._uniqueize(
                    build_openai_function_name(defn.server_key, t.name), used_names
                )
                openai_to_native[openai_name] = t.name
                tools.append(self._mcp_to_openai_tool(defn.server_key, openai_name, t))

            async def call_tool(openai_name: str, args: dict) -> str:
                native = openai_to_native.get(openai_name)
                if native is None:
                    return f"Unknown MCP tool mapping for: {openai_name}"
                try:
                    result = await asyncio.wait_for(
                        client.call_tool(native, args), timeout=self._timeout_s
                    )
                except asyncio.TimeoutError:
                    metrics.mcp_call_timeout.labels(server=defn.server_key).inc()
                    return f"MCP tool timeout after {self._timeout_s}s: {openai_name}"
                return self._serialize_result(result)

            async def close() -> None:
                try:
                    await transport_ctx.__aexit__(None, None, None)
                except Exception:
                    log.warning("[mcp] close failed key=%s", key, exc_info=True)

            session = PooledMcpSession(open_ai_tools=tools, call_tool=call_tool, close=close)
            self._sessions[key] = session
            metrics.mcp_session_open.labels(server=defn.server_key, source=defn.source).inc()
            return session
        except Exception:
            log.warning(
                "[mcp] failed to connect server %r (source=%s)",
                defn.server_key, defn.source, exc_info=True,
            )
            metrics.mcp_session_failed.labels(server=defn.server_key, source=defn.source).inc()
            return None

    @staticmethod
    def _uniqueize(base: str, used: set[str]) -> str:
        if base not in used:
            used.add(base)
            return base
        n = 2
        while f"{base}_{n}" in used:
            n += 1
        used.add(f"{base}_{n}")
        return f"{base}_{n}"

    @staticmethod
    def _mcp_to_openai_tool(server_key: str, openai_name: str, t: McpTool) -> dict:
        params = t.inputSchema if isinstance(t.inputSchema, dict) else {"type": "object", "properties": {}}
        desc = (t.description or "").strip() or t.name
        return {
            "type": "function",
            "function": {
                "name": openai_name,
                "description": f"[MCP {server_key}] {desc}",
                "parameters": params,
            },
        }

    @staticmethod
    def _serialize_result(result) -> str:
        # MCP CallToolResult: { isError, content[{type,text,...}], structuredContent }
        if getattr(result, "isError", False):
            return f"MCP tool error: {result!r}"
        parts: list[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
            else:
                parts.append(repr(block))
        sc = getattr(result, "structuredContent", None)
        if sc is not None:
            import json
            parts.append(json.dumps(sc, ensure_ascii=False))
        out = "\n".join(parts).strip()
        return out or "(empty MCP result)"

    async def evict_user_server(self, user_id: str, server_key: str) -> None:
        key = self._key(user_id, server_key)
        session = self._sessions.pop(key, None)
        self._inflight.pop(key, None)
        if session is not None:
            try:
                await session.close()
            except Exception:
                log.warning("[mcp] evict close failed key=%s", key, exc_info=True)

    async def close_all(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._inflight.clear()
        for s in sessions:
            try:
                await s.close()
            except Exception:
                log.warning("[mcp] close_all session failed", exc_info=True)
```

### 4.2 注册中心

```python
# src/agent_platform/infrastructure/mcp/registry.py
from __future__ import annotations
import logging
from typing import Iterable

from agent_platform.domain.mcp import McpServerDefinition, UserMcpRepository
from .session_pool import McpSessionPool
from .redact import redact_transport_for_display

log = logging.getLogger(__name__)
SYSTEM_SCOPE = "__system__"


class McpRegistry:
    def __init__(
        self,
        system_servers: Iterable[McpServerDefinition],
        user_repo: UserMcpRepository,
    ) -> None:
        self._system_servers = list(system_servers)
        self._user_repo = user_repo

    def _merge_for_user(self, user_rows: list[McpServerDefinition]) -> list[McpServerDefinition]:
        merged: dict[str, McpServerDefinition] = {s.server_key: s for s in self._system_servers}
        for u in user_rows:
            if u.server_key in merged:
                log.warning("[mcp] skip user MCP %r (conflicts with system)", u.server_key)
                continue
            merged[u.server_key] = u
        return list(merged.values())

    @staticmethod
    def _visible(defn: McpServerDefinition, agent_id: str) -> bool:
        if not defn.enabled:
            return False
        if defn.is_public:
            return True
        return agent_id in defn.agent_ids

    async def visible_definitions(self, agent_id: str, user_id: str) -> list[McpServerDefinition]:
        user_rows = await self._user_repo.list_by_user_id(user_id)
        merged = self._merge_for_user(user_rows)
        return [d for d in merged if self._visible(d, agent_id)]

    async def build_openai_tools(
        self, agent_id: str, user_id: str, pool: McpSessionPool
    ) -> list[dict]:
        defns = await self.visible_definitions(agent_id, user_id)
        out: list[dict] = []
        for defn in defns:
            scope = SYSTEM_SCOPE if defn.source == "system" else user_id
            session = await pool.get_session(defn, scope)
            if session is not None:
                out.extend(session.open_ai_tools)
        return out

    async def execute_mcp_tool(
        self,
        agent_id: str,
        user_id: str,
        pool: McpSessionPool,
        openai_function_name: str,
        args: dict,
    ) -> str | None:
        defns = await self.visible_definitions(agent_id, user_id)
        for defn in defns:
            scope = SYSTEM_SCOPE if defn.source == "system" else user_id
            session = await pool.get_session(defn, scope)
            if session is None:
                continue
            if not any(t["function"]["name"] == openai_function_name for t in session.open_ai_tools):
                continue
            return await session.call_tool(openai_function_name, args)
        return None

    async def list_catalog_for_display(self, user_id: str):
        user_rows = await self._user_repo.list_by_user_id(user_id)
        system_public = [s for s in self._system_servers if s.enabled and s.is_public]
        return {
            "system_public": [_with_redacted(s) for s in system_public],
            "user_servers": [_with_redacted(s) for s in user_rows],
        }


def _with_redacted(s: McpServerDefinition) -> McpServerDefinition:
    return McpServerDefinition(
        server_key=s.server_key,
        source=s.source,
        enabled=s.enabled,
        is_public=s.is_public,
        agent_ids=s.agent_ids,
        transport=redact_transport_for_display(s.transport),
    )
```

### 4.3 transport 工厂（最小骨架）

```python
# src/agent_platform/infrastructure/mcp/transport_factory.py
from contextlib import asynccontextmanager
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client


@asynccontextmanager
async def open_transport(transport_cfg: dict):
    kind = transport_cfg.get("type", "stdio")
    if kind == "stdio":
        params = StdioServerParameters(
            command=transport_cfg["command"],
            args=transport_cfg.get("args", []),
            env=transport_cfg.get("env"),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                yield session
    elif kind == "sse":
        async with sse_client(transport_cfg["url"], headers=transport_cfg.get("headers")) as (read, write):
            async with ClientSession(read, write) as session:
                yield session
    else:
        raise ValueError(f"unsupported MCP transport: {kind}")
```

### 4.4 ${VAR} 插值与脱敏

```python
# src/agent_platform/infrastructure/mcp/env_substitute.py
import os, re

_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")

def substitute(value):
    if isinstance(value, str):
        return _PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v) for v in value]
    return value
```

```python
# src/agent_platform/infrastructure/mcp/redact.py
SENSITIVE_KEYS = {"authorization", "x-api-key", "api_key", "apikey", "token", "password", "secret"}

def redact_transport_for_display(transport: dict) -> dict:
    out = dict(transport)
    if "headers" in out and isinstance(out["headers"], dict):
        out["headers"] = {
            k: ("***" if k.lower() in SENSITIVE_KEYS else v) for k, v in out["headers"].items()
        }
    if "env" in out and isinstance(out["env"], dict):
        out["env"] = {
            k: ("***" if k.lower() in SENSITIVE_KEYS or "secret" in k.lower() or "token" in k.lower() else v)
            for k, v in out["env"].items()
        }
    return out
```

## 5. 与现有 `agent-platform` 的集成

### 5.1 注入 `application/agent.py`

`agent.py` 在装配 `tools` 时新增一步 MCP tools 聚合：

```python
# 伪代码
mcp_tools = await registry.build_openai_tools(
    agent_id=ctx.agent_id, user_id=ctx.principal.id, pool=pool
)
all_tools = local_tools + mcp_tools
```

### 5.2 工具调度

`infrastructure/tools/runner.py` 在收到 `tool_calls` 时，先在本地 registry 里找；找不到再走 `registry.execute_mcp_tool(...)`；都没有命中再返回 `unknown tool`。

### 5.3 关闭与生命周期

在 FastAPI lifespan 钩子（`interfaces/api/app.py`）里：

```python
@asynccontextmanager
async def lifespan(app):
    pool = McpSessionPool(tool_timeout_ms=settings.mcp_tool_timeout_ms)
    # ... 注入容器
    yield
    await pool.close_all()
```

## 6. 配置（`.env.example` 增量）

```bash
# === MCP ===
MCP_SYSTEM_CONFIG_PATH=./config/mcp.system.yaml
MCP_TOOL_TIMEOUT_MS=60000
```

`config/mcp.system.yaml` 示例：

```yaml
servers:
  - server_key: filesystem
    enabled: true
    is_public: true
    transport:
      type: stdio
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "${WORKSPACE_ROOT}"]
  - server_key: jira
    enabled: true
    is_public: false
    agent_ids: ["stock-recap"]
    transport:
      type: sse
      url: https://internal.jira/mcp/sse
      headers:
        Authorization: "Bearer ${JIRA_TOKEN}"
```

## 7. 迁移步骤（建议拆 PR）

1. **PR-1（domain + types）**：新增 `domain/mcp.py`、`infrastructure/mcp/types.py / env_substitute.py / redact.py / parse_config.py / load_system_file.py`，加一份 mcp.system.yaml 样例。
2. **PR-2（pool + registry）**：新增 `transport_factory.py / naming.py / session_pool.py / registry.py`，单测覆盖（用 `pytest-asyncio` + 本地 echo MCP server）。
3. **PR-3（user repo）**：`infrastructure/persistence/repositories.py` 增加 `UserMcpRepository` 实现（SQL 表 `user_mcp_servers`，schema 见 `dataclaw/prisma/schema.prisma` 的 `UserMcpServer` 模型）。
4. **PR-4（注入 agent loop）**：在 `application/agent.py` / `infrastructure/tools/runner.py` 接入。
5. **PR-5（admin API）**：`interfaces/api/v1/admin/mcp.py`（list / upsert / delete + 触发 evict）。

## 8. 验收标准

- [ ] `pytest tests/unit/mcp -q` 全绿，覆盖率 ≥ 85%；
- [ ] 启动期能加载 `mcp.system.yaml` 至少 1 个 stdio + 1 个 sse server；
- [ ] `application/agent.py` 跑一次 turn 时，`tools` 列表里包含 MCP tools，命名形如 `mcp__filesystem__read_file`；
- [ ] 模拟 MCP server 故障时，`agent loop` 不抛异常，返回 "MCP tool error: ..." 字符串；
- [ ] `GET /v1/admin/mcp` 返回的 transport 中所有敏感字段为 `***`；
- [ ] `PUT /v1/admin/mcp/users/{user_id}/{server_key}` 后下次 turn 立即生效（pool evict）。

## 9. 对照源码

| dataclaw 文件 | agent-platform 目标文件 |
|---|---|
| `src/services/mcp/types.ts` | `infrastructure/mcp/types.py` + `domain/mcp.py` |
| `src/services/mcp/envSubstitute.ts` | `infrastructure/mcp/env_substitute.py` |
| `src/services/mcp/redactTransportForDisplay.ts` | `infrastructure/mcp/redact.py` |
| `src/services/mcp/parseConfig.ts` | `infrastructure/mcp/parse_config.py` |
| `src/services/mcp/loadSystemMcpFile.ts` | `infrastructure/mcp/load_system_file.py` |
| `src/services/mcp/transportFactory.ts` | `infrastructure/mcp/transport_factory.py` |
| `src/services/mcp/naming.ts` | `infrastructure/mcp/naming.py` |
| `src/services/mcp/mcpSessionPool.ts` | `infrastructure/mcp/session_pool.py` |
| `src/services/mcp/mcpRegistry.ts` | `infrastructure/mcp/registry.py` |
| `src/stores/userMcpStore.ts` + `prisma UserMcpServer` | `infrastructure/persistence/repositories.py` 的 `UserMcpRepository` |
