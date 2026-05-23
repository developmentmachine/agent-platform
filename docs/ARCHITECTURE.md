# Agent Platform — 架构总览（v2）

> 本文是 v2 平台化重构后的权威架构说明。
> **原 `docs/ARCHITECTURE_AND_BUSINESS.md` 仍是 stock-recap 业务说明，本文是平台说明，定位互补。**

---

## 1. 项目定位

**Agent Platform 是一个通用智能体运行平台**：

- 多 Agent：每个 use case 一个独立 Agent 包，互不依赖；
- 多入口：CLI / HTTP / WeCom / QQ / Scheduler / MCP-stdio 通过同一 Runtime；
- 工具走 MCP：进程内不再有 function-calling 私有注册表（迁移分阶段进行）；
- 插件化：Agent、Skill、Tool、LLM 后端均通过 `entry_points` 注册。

`stock-recap` 是平台上的**第一个**业务 Agent，验证整套平台契约。

---

## 2. 架构分层（六边形 / 端口与适配器）

```
 ┌──────────────────────────────────────────────────────────┐
 │ Driving Adapters                                         │
 │  CLI · HTTP/Webhook · WeCom AiBot · QQ Bot · Scheduler   │
 │  MCP-stdio (Agent 暴露面)                                 │
 └────────────────────────┬─────────────────────────────────┘
                          ↓ AgentRuntime.run / stream
 ┌──────────────────────────────────────────────────────────┐
 │ Runtime  (Composition Root)                              │
 │  AgentRuntime · create_runtime · SessionResolver         │
 │  Observability · Lifecycle                               │
 └────────────────────────┬─────────────────────────────────┘
                          ↓ AgentDefinition.runner / pipeline
 ┌──────────────────────────────────────────────────────────┐
 │ Orchestration  (泛型，与具体 Agent 解耦)                   │
 │  Phase[StateT] · Pipeline · RunState 基类                 │
 │  SideEffectBus · StreamEvent                              │
 └────────────────────────┬─────────────────────────────────┘
                          ↓
 ┌──────────────────────────────────────────────────────────┐
 │ Agents / <id>                                            │
 │  domain · phases · prompts · skills · data · effects     │
 └────────────────────────┬─────────────────────────────────┘
                          ↓
 ┌──────────────────────────────────────────────────────────┐
 │ Core / Ports                                             │
 │  LlmBackendPort · McpClientPort · MemoryPort · RepoPort  │
 │  RendererPort · GuardrailPort · PushPort · SessionPort   │
 └────────────────────────┬─────────────────────────────────┘
                          ↓ implements
 ┌──────────────────────────────────────────────────────────┐
 │ Infrastructure (Driven Adapters)                         │
 │  LLM providers · MCP client · SQLite/PG · Qdrant         │
 │  Push · Data adapters                                    │
 └──────────────────────────────────────────────────────────┘
```

---

## 3. 物理分层（src/agent_platform/）

| 包 | 角色 | 关键内容 |
|----|------|----------|
| `core/` | 平台契约层 | `ports/` · `runtime/` · `orchestration/` · `registry/` · `errors` |
| `runtime/` | Composition Root | `factory.create_runtime` · `AgentRuntime` · `StatelessSessionResolver` |
| `infra/` | Driven Adapters | `llm/` · `mcp_client/` · `persistence/` · `memory/` · `push/` · `guardrail/` |
| `tools_server/` | 独立 MCP server | `server.py` · `handlers/` |
| `agents/<id>/` | 业务 Agent（互相隔离） | `manifest.py` · `domain/` · `phases/` · `prompts/` · `skills/` |
| `adapters/` | Driving Adapters | `cli/` · `http/` · `wecom/` · `qq/` · `scheduler/` · `mcp_stdio/` |

> **当前状态**：`infra/*`、`adapters/*`、`runtime/*`（含 `observability`、`jobs`、`side_effects`）、`core/domain/*`、`agents/<id>/` 为唯一顶层包；原 `application/`、`domain/`、`infrastructure/`、`interfaces/`、`policy/`、`observability/`、`presentation/` 等遗留 shim **已删除**（W16）。

---

## 4. 依赖方向（import-linter 强制）

```
adapters/*       → runtime, core
runtime          → core, infra（通过 ports）, agents（仅 Composition Root 显式注册）
agents/<id>      → core, infra（通过 ports）
agents/<a>       ↛ agents/<b>          # 互相隔离
tools_server     → core.ports.mcp_tool, 各 handler
tools_server     ↛ agents              # 工具中立
infra/*          → core.ports
core             ↛ 任何上层
```

`pyproject.toml [tool.importlinter]` 已配置 4 条 contract，CI 跑 `lint-imports` 强制。

---

## 5. 平台扩展点（如何新增）

| 扩展点 | 怎么做 | 例子 |
|--------|--------|------|
| **新 Agent** | 新建 `agents/<id>/manifest.py`，导出 `register(reg)`；可选 entry_point | `stock-recap` |
| **新 LLM 后端** | 实现 `LlmBackendPort`，在 `infra/llm/providers` 注册 | `openai` / `ollama` |
| **新工具** | 在 `tools_server/handlers/` 加 handler，通过 MCP 自动可用 | `web_search` |
| **新接入入口** | 在 `adapters/<x>/` 实现 connector，统一调 `runtime.run(...)` | `wecom` / `qq` |
| **新 Renderer** | 实现 `RendererPort`，在 Agent manifest 中声明 | `wechat_text` |
| **新 Skill** | 包内或外部 bundle，通过 `agent_platform.skills` entry_point 注入 | 已有机制 |
| **新副作用** | Agent 在注册时通过 `SideEffectBus.subscribe(event, handler)` | `evolution` / `push` |

---

## 6. 关键平台组件

### 6.1 `AgentDefinition` + `AgentRegistry`

```python
# 注册一个 Agent
from agent_platform.core.registry import AgentDefinition, AgentRegistry, AgentCapability

def register(reg: AgentRegistry) -> None:
    reg.register(AgentDefinition(
        id="my-agent",
        display_name="My Agent",
        description="...",
        request_model=MyRequest,
        response_model=MyResponse,
        capabilities=[AgentCapability.CHAT, AgentCapability.STREAMING],
        runner=my_runner,                     # 或 chat_handler / pipeline_factory
        mcp_tool_names=["web_search"],
        skills=["my_skill"],
    ))
```

### 6.2 `Pipeline[StateT]` + `Phase[StateT]`

```python
from agent_platform.core.orchestration import Pipeline, Phase

class MyPhase(Phase[MyState]):
    name = "my_phase"
    def run(self, state: MyState) -> None: ...
    def stream(self, state: MyState) -> Iterator[StreamEvent]: ...

pipeline = Pipeline([MyPhase(), AnotherPhase()])
pipeline.execute(state)            # 同步
list(pipeline.stream(state))       # NDJSON 流
```

### 6.3 `SideEffectBus`

```python
from agent_platform.core.orchestration import SideEffectBus, StandardEvent

bus = SideEffectBus()
bus.subscribe(StandardEvent.RUN_COMPLETED, lambda ctx: push_to_wecom(ctx))
bus.subscribe(StandardEvent.RUN_PERSISTED, lambda ctx: run_backtest(ctx))
```

### 6.4 `AgentRuntime`

```python
from agent_platform.runtime import create_runtime
from agent_platform.core.runtime.principal import PrincipalContext

runtime = create_runtime()
resp = runtime.run(
    agent_id="stock-recap",
    payload={"mode": "daily", "provider": "live"},
    principal=PrincipalContext.anonymous(source="cli"),
    conversation_key="cli:user",
)
```

### 6.5 MCP-Only 工具栈

- `core.ports.mcp_tool.McpClientPort` 是唯一工具通道；
- `infra/mcp_client/stdio.StdioMcpClient` 是默认实现（本地子进程跑 `tools_server`）；
- `infra/mcp_client/http.HttpMcpClient` 与 `MultiMcpRouter` 留作后续 commit；
- 工具治理（白名单 / 角色 / per-tool budget / 审计 / 超时）由 `runtime.McpToolGateway`
  在 Port 外围统一包装（**当前**：现有 `RecapToolRunner` 仍承担此职责，未来 commit 抽出）。

---

## 7. 迁移路线图（refactor/v2-platform 分支）

| 阶段 | 内容 | 当前状态 |
|------|------|----------|
| **W1：结构重构** | 新顶层包骨架 + Ports + Pipeline + Registry + Bus + 入口适配 + WeCom/QQ 骨架 + 文档 + import-linter | ✅ 已完成 |
| **W2：MCP 物理切换** | `tools_server` 独一真实源；`RecapToolRunner` → `McpToolGateway` | ✅ 已完成 |
| **W3：recap 物理迁入 `agents/stock_recap/`** | data / llm / effects / prompts / skills / cli / http_routes | ✅ 已完成 |
| **W4：recap 类化为 `Phase`** | `_phase_*` → Phase 子类；`pipeline_v2` 并行入口 | ✅ 已完成 |
| **W5：WeCom/QQ SDK 接入** | QQ botpy WS + 企微 AES webhook + 企微 AiBot WebSocket | ✅ 已完成 |
| **W6：CLI/HTTP/Scheduler 自动装配** | `AgentRegistry` 驱动，无硬编码 AGENTS | ✅ 已完成 |
| **W7：删 deprecation shim** | 全库 canonical import；CI `lint-imports` | ✅ 已完成 |
| **W8：infra / adapters 物理迁移** | `infrastructure/*` → `infra/*`；`interfaces/*` → `adapters/*`；旧路径 shim | ✅ 已完成 |
| **W9：observability / budget / RunContext** | → `runtime/observability`、`core/runtime/*`；旧路径 shim | ✅ 已完成 |
| **W10：policy → guardrail** | `policy/` → `infra/guardrail/`（含 `rules.yaml`）；旧路径 shim | ✅ 已完成 |
| **W11：domain 平台模块** | `domain/models` 等 → `core/domain/*`；`principal` / `run_context` 仍为 shim | ✅ 已完成 |
| **W12：application 平台代码** | `side_effects` / `jobs` → `runtime/`；`backtest/registry` → `agents/stock_recap/backtest/`；`application/*` shim | ✅ 已完成 |
| **W13：presentation 收尾** | 展示逻辑在 `agents/<id>/render.py`；`presentation/render` 为 shim | ✅ 已完成 |
| **W14：Principal 合并** | `domain.principal` 与 `core.runtime.principal` 合一；单一 ContextVar | ✅ 已完成 |
| **W15：canonical import** | 业务代码统一 `core.runtime` / `runtime` / `agents` 路径；import-linter 禁止遗留顶层包 | ✅ 已完成 |
| **W16：删除 shim 包** | 物理移除 `application/`、`domain/`、`infrastructure/`、`interfaces/`、`policy/`、顶层 `observability/`、`presentation/` | ✅ 已完成 |

---

## 8. 与原 4 层对照表

| 原 4 层 | v2 新位置 | 说明 |
|---------|----------|------|
| `interfaces/` | `adapters/` | 入口适配器；新增 `wecom/` `qq/` |
| `application/recap.py` | `agents/stock_recap/manifest.py` 调用 | recap 入口收敛到 Agent manifest |
| `application/orchestration/` | `core/orchestration/`（泛型）+ `agents/stock_recap/`（recap 专用） | 编排引擎与具体 Agent 解耦 |
| `application/side_effects/` | `runtime/side_effects/`（outbox/deferred）+ `agents/stock_recap/effects/`（业务动作） | Composition Root 可触达 infra/agents |
| `application/jobs.py` | `runtime/jobs.py` | 调度/API 共用任务定义 |
| `application/backtest/registry.py` | `agents/stock_recap/backtest/registry.py` | 策略注册与 recap Agent 绑定 |
| `domain/` | `core/domain/`（平台模型/仓储/注册表）+ `agents/stock_recap/domain/`（业务类型） | `domain/*` 子路径为 shim |
| `infrastructure/` | `infra/` | 已物理迁移；`infrastructure/*` 为 shim |
| `interfaces/` | `adapters/` | 已物理迁移；`interfaces/*` 为 shim |
| `observability/` | `runtime/observability/` | 旧顶层包为 shim |
| `policy/` | `infra/guardrail/` | recap 输出规则仍在 `agents/stock_recap/` |
| `presentation/` | `agents/<id>/render.py` | 例：`agents/stock_recap/render.py`；`presentation/render` 为 shim |
| `interfaces/mcp_stdio.py` | `tools_server/server.py` + `adapters/mcp_stdio/` | 工具服务 vs Agent 服务分开 |

---

## 9. 参考

- `docs/ADR/ADR-001-v2-platformization.md` — 本次重构的决策记录
- `docs/extending-agents.md` — 新增 Agent 操作手册
- `docs/ARCHITECTURE_AND_BUSINESS.md` — stock-recap 业务说明（与本文互补）
