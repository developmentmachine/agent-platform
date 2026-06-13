# Agent Platform — 架构总览（v2）

> 本文是 v2 平台化重构后的权威架构说明。
> **原 `docs/ARCHITECTURE_AND_BUSINESS.md` 仍是 stock-recap 业务说明，本文是平台说明，定位互补。**

---

## 1. 项目定位

**Agent Platform 是一个通用智能体运行平台**：

- 多 Agent：每个 use case 一个独立 Agent 包，互不依赖；
- 多入口：CLI / HTTP / WeCom / QQ / Scheduler / MCP-stdio 通过同一 Runtime；
- 工具走 MCP：进程内不再有 function-calling 私有注册表（迁移分阶段进行）；
- 插件化：Agent、Skill、Tool、LLM 后端均通过 `entry_points` 注册；
- **可拆分打包**：core / infra / agent 可独立构建 wheel，按需组装。

当前内置业务 Agent：

| ID | 包路径 | 能力概要 |
|----|--------|----------|
| `stock-recap` | `agents/stock_recap/` | 报告、NDJSON 流、定时任务、MCP 工具、Skills |
| `hsk30-tutor` | `agents/hsk30_tutor/` | HSK 3.0 多轮对话陪练（CHAT）、字词约束验证、自动重试修正、流式输出 |

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
│  AgentRuntime · create_runtime · AgentScope 裁剪         │
│  validate_agent_dependencies · SessionResolver           │
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
│  deps.py (DI 容器) · manifest.py (注册)                   │
└────────────────────────┬─────────────────────────────────┘
                         ↓ 端口协议（零 infra 引用）
┌──────────────────────────────────────────────────────────┐
│ Core / Ports                                             │
│  LlmBackendPort · McpClientPort · MemoryPort · RepoPort  │
│  RendererPort · GuardrailPort · PushPort · SessionPort   │
│  AgentApp (独立运行容器)                                   │
└────────────────────────┬─────────────────────────────────┘
                         ↓ implements
┌──────────────────────────────────────────────────────────┐
│ Infrastructure (Driven Adapters)                         │
│  LLM providers · MCP client · SQLite/PG · Qdrant         │
│  Push · Guardrail · Memory · Embeddings                  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 物理分层与独立包

### 3.1 源码结构（monolith 为 source of truth）

```
src/agent_platform/
├── core/                   ← Layer 0: 平台契约（0 外部依赖，0 上层引用）
│   ├── ports/              ← 11 个端口协议（Protocol）
│   ├── runtime/            ← AgentScope, RunContext, Tracing, Metrics
│   ├── orchestration/      ← Pipeline, Phase, SideEffectBus
│   ├── registry/           ← AgentDefinition, AgentRegistry
│   ├── app.py              ← AgentApp（独立运行容器）
│   ├── config/             ← Settings, 配置管理
│   ├── domain/             ← 领域模型（Recap, GenerateRequest 等）
│   └── utils/              ← stable_json, utc_now_iso 等
├── infra/                  ← Layer 1: 端口实现（依赖 core）
│   ├── persistence/        ← SQLite repos, init_db
│   ├── llm/                ← LLM backends, providers
│   ├── push/               ← WeChat push
│   ├── policy/             ← Guardrail 实现
│   ├── memory/             ← Embeddings, VectorStore
│   └── embeddings/         ← OpenAI embeddings
├── agents/                 ← Layer 2: 业务 Agent（依赖 core，lazy 引用 infra）
│   ├── stock_recap/        ← 73 files, 通过 deps.py DI
│   └── hsk30_tutor/        ← 11 files, 纯 core 引用
├── adapters/               ← Layer 3: Driving Adapters
├── runtime/                ← Composition Root (factory.py)
└── tools_server/           ← MCP 工具服务
```

### 3.2 独立 wheel 包

| 包名 | 内容 | 文件数 | 依赖 |
|------|------|--------|------|
| `agent-platform-core` | ports + domain + config + runtime + AgentApp | 44 | 无外部依赖 |
| `agent-platform-infra` | SQLite/LLM/push/guardrail/memory 实现 | 48 | core |
| `agent-platform-stock-recap` | stock_recap agent | 73 | core + infra |
| `agent-platform-hsk30-tutor` | hsk30_tutor agent | 11 | core + infra |
| `agent-platform` (monolith) | 完整运行时: CLI/HTTP/Scheduler/Bot | 全部 | core + infra + all agents |

### 3.3 依赖方向（import-linter 强制）

```
adapters/*       → runtime, core
runtime          → core, infra（通过 ports）, agents（仅 Composition Root 显式注册）
agents/<id>      → core（模块级）, infra（仅函数内 lazy import）
agents/<a>       ↛ agents/<b>          # 互相隔离
infra/*          → core.ports
core             ↛ 任何上层
```

**关键约束**：
- `core → 上层`：**0** 模块级引用（import-linter 强制）
- `agents → infra`：**0** 模块级引用（全部通过 DI / lazy import）
- `agents ↔ agents`：**0** 互引

`pyproject.toml [tool.importlinter]` 已配置 4 条 contract，CI 跑 `lint-imports` 强制。

---

## 4. 依赖注入（DI）模式

### 4.1 端口协议（core/ports/）

```python
# core/ports/llm.py
@runtime_checkable
class LlmBackendPort(Protocol):
    def call(self, messages, **kwargs) -> Tuple[str, LlmTokens]: ...

# core/ports/repository.py
@runtime_checkable
class RepositoryFactoryPort(Protocol):
    def run_repository(self) -> RunRepository: ...
    def feedback_repository(self) -> FeedbackRepository: ...
    # ... 共 6 个 repo

# core/ports/guardrail.py
@runtime_checkable
class GuardrailPort(Protocol):
    def validate_generate_request(self, req) -> None: ...
    def clamp_messages(self, messages, max_chars) -> List[dict]: ...
    def coerce_recap_output(self, recap, *args, **kwargs) -> Any: ...
```

### 4.2 Agent DI 容器（agents/<id>/deps.py）

```python
# agents/stock_recap/deps.py
@dataclass
class StockRecapDeps:
    repo_factory: RepositoryFactoryPort
    guardrail: GuardrailPort
    memory_factory: Optional[Callable] = None
    llm_caller: Optional[Callable] = None
    push_provider_factory: Optional[Callable] = None
    init_db: Optional[Callable[[str], None]] = None

# Bootstrap（monolith / CLI / HTTP 入口调用一次）
configure_default_deps(
    repo_factory=SqliteRepositoryFactory(db_path),
    guardrail=GuardrailAdapter(),
    init_db=init_db,
    ...
)

# 业务代码
deps = default_deps()
repo = deps.repo_factory.run_repository()
```

### 4.3 独立运行（AgentApp）

```python
from agent_platform.core.app import AgentApp

# 不依赖 monolith，只需 core + infra + agent wheel
app = AgentApp(
    agent_id="stock-recap",
    llm=my_llm_backend,
    repo_factory=my_repo_factory,
)
result = app.run(payload={"mode": "daily", "provider": "live"})
```

---

## 5. Agent 自动发现

### 5.1 entry_points 机制

```toml
# packages/stock-recap/pyproject.toml
[project.entry-points."agent_platform.agents"]
stock-recap = "agent_platform.agents.stock_recap.manifest:register"
```

```python
# runtime/factory.py — 自动发现
from importlib.metadata import entry_points

for ep in entry_points(group="agent_platform.agents"):
    register = ep.load()
    register(registry)
```

### 5.2 发现链路

```
pip install agent-platform-stock-recap
    ↓ entry_points 写入 dist-info/entry_points.txt
AgentApp / create_runtime / CLI
    ↓ importlib.metadata.entry_points(group="agent_platform.agents")
    ↓ 自动调用 register(registry)
Agent 可用
```

**无需修改任何平台文件** — 只要 wheel 声明了 entry_points，安装后自动发现。

---

## 6. 打包与发布

### 6.1 uv workspace（monolith 作为 source of truth）

```toml
# 根 pyproject.toml
[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
agent-platform-core = { workspace = true }
agent-platform-infra = { workspace = true }
agent-platform-stock-recap = { workspace = true }
agent-platform-hsk30-tutor = { workspace = true }
```

### 6.2 包结构（symlink 模式）

```
packages/
├── core/
│   ├── pyproject.toml          ← 构建配置
│   └── src/agent_platform → symlink → ../../../src/agent_platform
├── infra/
│   ├── pyproject.toml
│   └── src/agent_platform → symlink
├── stock-recap/
│   ├── pyproject.toml          ← only-include: agents/stock_recap
│   └── src/agent_platform → symlink
└── hsk30-tutor/
    ├── pyproject.toml          ← only-include: agents/hsk30_tutor
    └── src/agent_platform → symlink
```

### 6.3 构建命令

```bash
# 构建全部
cd packages/core && uv build --no-cache
cd packages/infra && uv build --no-cache
cd packages/stock-recap && uv build --no-cache
cd packages/hsk30-tutor && uv build --no-cache

# 独立安装验证
pip install dist/agent_platform_core-0.1.0-py3-none-any.whl
pip install dist/agent_platform_infra-0.1.0-py3-none-any.whl
pip install dist/agent_platform_stock_recap-0.1.0-py3-none-any.whl
```

详细打包指南见 [`docs/packaging.md`](./packaging.md)。

---

## 7. 平台扩展点（如何新增）

| 扩展点 | 怎么做 | 例子 |
|--------|--------|------|
| **新 Agent** | 新建 `agents/<id>/manifest.py`，导出 `register(reg)`；声明 entry_point | `stock-recap`、`hsk30-tutor` |
| **新 LLM 后端** | 实现 `LlmBackendPort`，在 `infra/llm/providers` 注册 | `openai` / `ollama` |
| **新工具** | `tools_server/tools/` 登记 SPEC；进入全局 MCP 池 | `web_search` |
| **新接入入口** | 在 `adapters/<x>/` 实现 connector，统一调 `runtime.run(...)` | `wecom` / `qq` |
| **新 Renderer** | 实现 `RendererPort`，在 Agent manifest 中声明 | `wechat_text` |
| **新 Skill** | `SKILL.md` 的 `name` 为 id；`manifest.json` 只写 `path`；entry_point + `with_skill_bundle` | stock-recap bundle |
| **新副作用** | Agent 在注册时通过 `SideEffectBus.subscribe(event, handler)` | `evolution` / `push` |
| **选择性部署** | 设置 `AGENTS_ENABLED` 环境变量（逗号分隔 Agent ID），`_register_builtin_agents` 按需注册 | `AGENTS_ENABLED=hsk30-tutor` |

详细新 Agent 指导见 [`docs/extending-agents.md`](./extending-agents.md)。

---

## 8. 关键平台组件

### 8.1 `AgentDefinition` + `AgentRegistry`

**依赖与运行期裁剪**：

- **注册时**：`create_runtime()` 注入 `validate_agent_dependencies`，`register()` 前核对声明 ⊆ 全局 skill/MCP 池。
- **运行时**：`AgentScope`（`current_agent_scope`）在 `agent_execution()` / `generate_once` / `AgentRuntime.run()` 激活；MCP = 平台已启用工具 ∩ 该 Agent 的 `mcp_tool_names`；skill overlay = 该 Agent 的 `skill_mode_map`。

### 8.2 Skills 与 MCP：全局池 + Agent 白名单

| 资源 | 全局池（登记 / 目录） | Agent 声明（`AgentDefinition`） | 运行期（`AgentScope`） |
|------|----------------------|----------------------------------|------------------------|
| **MCP 工具** | `tools_server/registry.py` | `mcp_tool_names` | 暴露给 LLM = 平台已启用 ∩ `mcp_tool_names` |
| **Skill 正文** | `skills.loader` 合并各 bundle | `skills` + `skill_mode_map` | overlay 只用本 Agent 的 `skill_mode_map` |

### 8.3 `Pipeline[StateT]` + `Phase[StateT]`

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

### 8.4 `AgentRuntime`

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

---

## 9. 迁移路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| W1-W7 | 结构重构 → MCP → 物理迁入 → Phase 类化 → WeCom/QQ → 自动装配 → 删 shim | ✅ 已完成 |
| W8 | core/infra/agent 独立打包 + DI + entry_points 自动发现 | ✅ 已完成 |
| W9 | AgentApp standalone bootstrap + 零 infra 引用 | ✅ 已完成 |

---

## 10. 参考

- [`docs/ARCHITECTURE_AND_BUSINESS.md`](./ARCHITECTURE_AND_BUSINESS.md) — stock-recap 业务说明
- [`docs/extending-agents.md`](./extending-agents.md) — 新增 Agent 操作手册
- [`docs/packaging.md`](./packaging.md) — 打包与发布指南
- [`docs/ADR/ADR-001-v2-platformization.md`](./ADR/ADR-001-v2-platformization.md) — 决策记录
