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

当前内置业务 Agent：

| ID | 包路径 | 能力概要 |
|----|--------|----------|
| `stock-recap` | `agents/stock_recap/` | 报告、NDJSON 流、定时任务、MCP 工具、Skills |
| `hsk30-tutor` | `agents/hsk30_tutor/` | HSK 3.0 多轮对话陪练（CHAT）、字词约束验证、自动重试修正、流式输出 |

`stock-recap` 是第一个完整验证平台契约的 Agent；`hsk30-tutor`（W17+）验证第二 Agent 的 CLI/HTTP 自动装配与业务隔离，并展示了**纯业务 Agent**的最佳实践（只依赖 `core.*`，不碰 `infra.*`）。

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
| `runtime/` | Composition Root | `create_runtime` · `AgentRuntime` · `scope.agent_execution` · `agent_validation` |
| `core/runtime/agent_scope.py` | 运行期白名单 | `AgentScope` · `current_agent_scope`（MCP ∩ 声明、skill 按 Agent mode 表） |
| `infra/` | Driven Adapters | `llm/` · `mcp_client/` · `persistence/` · `memory/` · `push/` · `guardrail/` |
| `tools_server/` | 独立 MCP server | `server.py` · `handlers/` |
| `agents/<id>/` | 业务 Agent（互相隔离） | `manifest.py` · `domain/` · `phases/` · `prompts/` · `skills/` |
| `adapters/` | Driving Adapters | `cli/` · `http/` · `wecom/` · `qq/` · `scheduler/` · `mcp_stdio/` |
| `application/` 等 | **迁移中：老 4 层路径** | 与 v2 路径并存；后续 commit 逐步迁入 v2 路径 |

> **当前 commit 的迁移策略**：core / runtime / agents / adapters / tools_server / infra 是**新的规范路径**；
> infrastructure / interfaces / application / domain / observability / policy / presentation 仍是**真实代码所在**。
> 两套路径**完全等价**，业务代码与测试无任何破坏。后续 commit 将物理迁移代码并把旧路径转为 shim。

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
| **新 Agent** | 新建 `agents/<id>/manifest.py`，导出 `register(reg)`；可选 entry_point | `stock-recap`、`hsk30-tutor` |
| **新 LLM 后端** | 实现 `LlmBackendPort`，在 `infra/llm/providers` 注册 | `openai` / `ollama` |
| **新工具** | `tools_server/tools/` 登记 SPEC；进入全局 MCP 池 | `web_search` |
| **新接入入口** | 在 `adapters/<x>/` 实现 connector，统一调 `runtime.run(...)` | `wecom` / `qq` |
| **新 Renderer** | 实现 `RendererPort`，在 Agent manifest 中声明 | `wechat_text` |
| **新 Skill** | `SKILL.md` 的 `name` 为 id；`manifest.json` 只写 `path`；entry_point + `with_skill_bundle` | stock-recap bundle |
| **新副作用** | Agent 在注册时通过 `SideEffectBus.subscribe(event, handler)` | `evolution` / `push` |
| **选择性部署** | 设置 `AGENTS_ENABLED` 环境变量（逗号分隔 Agent ID），`_register_builtin_agents` 按需注册 | `AGENTS_ENABLED=hsk30-tutor` |

> **选择性部署示例：**
> ```bash
> # 只部署 hsk30-tutor
> AGENTS_ENABLED=hsk30-tutor uv run agent-platform stock-recap --serve
> # 只部署 stock-recap
> AGENTS_ENABLED=stock-recap uv run agent-platform stock-recap --serve
> # 全部部署（默认）
> uv run agent-platform stock-recap --serve
> ```

---

## 6. 关键平台组件

### 6.1 `AgentDefinition` + `AgentRegistry`

**依赖与运行期裁剪**：

- **注册时**：`create_runtime()` 注入 `validate_agent_dependencies`，`register()` 前核对声明 ⊆ 全局 skill/MCP 池。
- **运行时**：`AgentScope`（`current_agent_scope`）在 `agent_execution()` / `generate_once` / `AgentRuntime.run()` 激活；MCP = 平台已启用工具 ∩ 该 Agent 的 `mcp_tool_names`；skill overlay = 该 Agent 的 `skill_mode_map`（正文仍从全局 skill 目录按 id 加载）。全局合并的 `mode_to_skill_id` 仅用于目录/运维，**不**驱动 Agent prompt。

```python
# 推荐：经 create_runtime 注册（内置校验）
from agent_platform.runtime import create_runtime

runtime = create_runtime()  # 内部 register 内置/发现的 Agent 时已校验依赖

# 第三方 Agent manifest 示例
from agent_platform.core.registry import AgentDefinition, AgentRegistry, AgentCapability
from agent_platform.skills.bundle import with_skill_bundle

def register(reg: AgentRegistry) -> None:
    defn = AgentDefinition(
        id="my-agent",
        display_name="My Agent",
        description="...",
        request_model=MyRequest,
        response_model=MyResponse,
        capabilities=[AgentCapability.CHAT, AgentCapability.TOOL_USING],
        runner=my_runner,
        mcp_tool_names=["web_search"],  # 须在 tools_server 中存在
    )
    reg.register(with_skill_bundle(defn, bundle_key="my-agent"))  # skills 从 SKILL.md 自动识别
```

业务入口须在 **`agent_execution(defn)`** 或 `generate_once` / `AgentRuntime.run` 内激活 `AgentScope`；否则 skill overlay 与 MCP 裁剪不生效。

### 6.2 Skills 与 MCP：全局池 + Agent 白名单

| 资源 | 全局池（登记 / 目录） | Agent 声明（`AgentDefinition`） | 运行期（`AgentScope`） |
|------|----------------------|----------------------------------|------------------------|
| **MCP 工具** | `tools_server/registry.py` | `mcp_tool_names` | 暴露给 LLM = 平台已启用 ∩ `mcp_tool_names`；`execute` 越权拒绝 |
| **Skill 正文** | `skills.loader` 合并各 bundle（按 id 读文件） | `skills` + `skill_mode_map`（`with_skill_bundle` 填充） | overlay 只用本 Agent 的 `skill_mode_map`，不用全局 `mode_to_skill_id` |

**Skill id 真源**：各 `SKILL.md` frontmatter 的 `name`；`manifest.json` 的 `skills[]` **只写 `path`**（禁止写 `id`，加载时自动解析）。

**`RECAP_SKILL_EXTRA_DIRS`**：向全局 skill **目录**追加条目；要改变某 Agent 的 mode→skill 映射，改该 Agent 的 bundle 或 `RECAP_SKILL_ID`（须在 `skills` 白名单内）。

### 6.3 `Pipeline[StateT]` + `Phase[StateT]`

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

### 6.4 `SideEffectBus`

```python
from agent_platform.core.orchestration import SideEffectBus, StandardEvent

bus = SideEffectBus()
bus.subscribe(StandardEvent.RUN_COMPLETED, lambda ctx: push_to_wecom(ctx))
bus.subscribe(StandardEvent.RUN_PERSISTED, lambda ctx: run_backtest(ctx))
```

### 6.5 `AgentRuntime`

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
| **W5：WeCom/QQ SDK 接入** | botpy WS + 企微 AES webhook | ✅ 已完成 |
| **W6：CLI/HTTP/Scheduler 自动装配** | `AgentRegistry` 驱动，无硬编码 AGENTS | ✅ 已完成 |
| **W7：删 deprecation shim** | 全库 canonical import；CI `lint-imports` | ✅ 已完成 |

---

## 8. 与原 4 层对照表

| 原 4 层 | v2 新位置 | 说明 |
|---------|----------|------|
| `interfaces/` | `adapters/` | 入口适配器；新增 `wecom/` `qq/` |
| `application/recap.py` | `agents/stock_recap/manifest.py` 调用 | recap 入口收敛到 Agent manifest |
| `application/orchestration/` | `core/orchestration/`（泛型）+ `agents/stock_recap/`（recap 专用） | 编排引擎与具体 Agent 解耦 |
| `application/side_effects/` | `core/orchestration/side_effects_bus`（机制）+ `agents/stock_recap/effects/`（订阅） | 副作用走总线 |
| `domain/` | `core/runtime/`（平台类型）+ `agents/stock_recap/domain/`（业务类型） | 拆分中 |
| `infrastructure/` | `infra/` | 别名等价；后续物理迁移 |
| `observability/` | `runtime/observability/`（W1 仍保持老路径） | |
| `policy/` | 通用部分 → `infra/guardrail/`；recap 输出规则 → `agents/stock_recap/` | |
| `presentation/` | `agents/<id>/render.py`（每 Agent 自带） | |
| `interfaces/mcp_stdio.py` | `tools_server/server.py` + `adapters/mcp_stdio/` | 工具服务 vs Agent 服务分开 |

---

## 9. 参考

- `docs/ADR/ADR-001-v2-platformization.md` — 本次重构的决策记录
- `docs/extending-agents.md` — 新增 Agent 操作手册
- `docs/ARCHITECTURE_AND_BUSINESS.md` — stock-recap 业务说明（与本文互补）
