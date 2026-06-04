# 扩展新 Agent 指导手册

> **v2 平台化架构**：新 Agent 必须放在 `src/agent_platform/agents/<id>/`，通过 `AgentDefinition` + `manifest.register` 接入。  
> 完整分层见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。内置示例：`stock-recap`、`hsk30-tutor`。

---

## 〇、TL;DR（最小新 Agent 5 步）

```
1) 新建 src/agent_platform/agents/<id>/（models · use_case · manifest.py）
2) 实现 runner（或 Pipeline[StateT] + Phase 子类）
3) manifest.py：reg.register(AgentDefinition(...))
4) runtime/factory.py → register_builtin_agents 加一行
   （可选：pyproject [project.entry-points."agent_platform.agents"])
5) pytest + uv run lint-imports
```

在 manifest 中声明 `cli_subparser_factory` / `cli_run_handler` 后，CLI 子命令自动出现；声明 `http_router_factories` 后，`stock-recap --serve` 启动的 API 会自动挂载路由。**无需修改** `adapters/cli/main.py`。

---

## 一、平台分层（你要动哪里）

| 层 | 路径 | 新 Agent 时 |
|----|------|-------------|
| `core/` | 契约、Pipeline、Registry | **不改** |
| `runtime/` | `factory.create_runtime` | 仅在 `register_builtin_agents` 加一行 |
| `infra/` | LLM、DB、MCP client | 一般不改 |
| `tools_server/` | MCP 工具 | 仅加新工具时改 |
| `agents/<id>/` | 业务代码 | ✅ 全部在这里 |
| `adapters/` | CLI / HTTP / QQ / 调度 | 一般不改 |

**Agent 之间禁止互相 import**（`import-linter` 强制）。

---

## 二、参考实现

| Agent | 目录 | 能力 | 要点 |
|-------|------|------|------|
| `stock-recap` | `agents/stock_recap/` | REPORT, STREAMING, SCHEDULED, TOOL_USING | Phase pipeline、skills、MCP 工具名、定时任务 |
| `hsk30-tutor` | `agents/hsk30_tutor/` | CHAT | 轻量 `chat_completion`、交互 REPL、`POST /v1/hsk30-tutor/chat` |

阅读顺序：`manifest.py` → `use_case.py`（或 `pipeline_v2.py`）→ `cli.py` → `http_routes.py`。

---

## 三、manifest 最小示例

### 3.1 纯对话 Agent（无 MCP / 无 Skill）

```python
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
)
from agent_platform.core.registry.agent_registry import AgentRegistry

AGENT_ID = "my-agent"


def _runner(*, envelope, principal, session, run_ctx, settings, runtime):
    # envelope.payload → 业务逻辑 → AgentResponseEnvelope
    ...


def register(registry: AgentRegistry) -> None:
    registry.register(
        AgentDefinition(
            id=AGENT_ID,
            display_name="My Agent",
            description="...",
            request_model=MyRequest,
            response_model=MyResponse,
            capabilities=[AgentCapability.CHAT],
            runner=_runner,
            mcp_tool_names=[],  # 无工具
            cli_help="一句话 help",
            http_path_prefix="/v1/my-agent",
            cli_subparser_factory=_cli_subparser,
            cli_run_handler=_cli_run,
            http_router_factories=[lambda: [my_router]],
        )
    )
```

`use_case` 入口须激活 `AgentScope`（`AgentRuntime.run` 已内置；直连 `use_case` 时自行包一层）：

```python
from agent_platform.runtime.scope import agent_execution

def chat_turn(req, settings, *, ctx=None):
    with agent_execution(_definition_for_registry()):  # 或缓存 manifest 里的 AgentDefinition
        ...
```

### 3.2 带 MCP + Skill bundle（报告 / 工具型）

**目录**（示例）：

```
agents/my_agent/
  manifest.py
  skills/
    manifest.json          # 只写 path + mode_to_skill_id，不写 id
    daily_task/SKILL.md    # frontmatter name: my_agent.daily  ← skill id 真源
  ...
```

`skills/manifest.json`：

```json
{
  "bundle_version": "1.0.0",
  "mode_to_skill_id": { "daily": "my_agent.daily" },
  "skills": [{ "path": "daily_task/SKILL.md", "description": "日终任务规程" }]
}
```

`pyproject.toml`（与 `stock-recap` 相同模式）：

```toml
[project.entry-points."agent_platform.agents"]
my-agent = "agent_platform.agents.my_agent.manifest:register"

[project.entry-points."agent_platform.skills"]
my-agent = "agent_platform.agents.my_agent.skills:bundle_root"
```

`agents/my_agent/skills/__init__.py`：

```python
from pathlib import Path

def bundle_root() -> Path:
    return Path(__file__).resolve().parent
```

`manifest.py`：

```python
from agent_platform.agents.my_agent.skills import bundle_root
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
)
from agent_platform.core.registry.agent_registry import AgentRegistry
from agent_platform.skills.bundle import with_skill_bundle

AGENT_ID = "my-agent"


def _runner(*, envelope, principal, session, run_ctx, settings, runtime):
    ...


def _build_definition() -> AgentDefinition:
    defn = AgentDefinition(
        id=AGENT_ID,
        display_name="My Agent",
        description="...",
        request_model=MyRequest,
        response_model=MyResponse,
        capabilities=[AgentCapability.REPORT, AgentCapability.TOOL_USING],
        runner=_runner,
        mcp_tool_names=["web_search"],  # ⊆ tools_server 全局池
        cli_help="...",
        http_path_prefix="/v1/my-agent",
        cli_subparser_factory=_cli_subparser,
        cli_run_handler=_cli_run,
        http_router_factories=[lambda: [my_router]],
    )
    return with_skill_bundle(
        defn,
        bundle_key="my-agent",       # 与 entry_point 名一致
        bundle_root=bundle_root(),
    )


def register(registry: AgentRegistry) -> None:
    registry.register(_build_definition())
```

构建 prompt 时用 `load_skill_overlay_for_mode(mode)`（要求当前线程已 `agent_execution`）；**不要**手写 `skills=[...]`。

### 3.3 注册与校验

- `create_runtime()` 会注入 `validate_agent_dependencies`：`register()` 前检查 MCP/skill 声明 ⊆ 全局池，且与 bundle 解析结果一致。
- 运行期：`AgentScope` = 平台已启用工具 ∩ `mcp_tool_names`；skill overlay = 本 Agent 的 `skill_mode_map`（见 [ARCHITECTURE.md §6.2](ARCHITECTURE.md)）。

注册后验证：

```bash
uv run agent-platform --list-agents
uv run agent-platform my-agent --help
```

---

## 四、Skills / MCP / Prompts

### 4.1 MCP 工具

1. 在 `tools_server/tools/` 增加 `SPEC`，由 `tools_server/registry.py` 聚合（**全局池**）。
2. 在 `AgentDefinition` 声明 `mcp_tool_names=[...]`（该 Agent 允许的工具子集）。
3. 运行期：`AgentScope` 将暴露给 LLM 的工具裁成 **平台已启用 ∩ mcp_tool_names**（`create_runtime` → `agent_execution` / `generate_once` / `AgentRuntime.run` 内激活）。

无 skill、无工具的 Agent（如 `hsk30-tutor`）保持 `mcp_tool_names=[]` 即可。

### 4.2 Skills（bundle）

| 写什么 | 位置 |
|--------|------|
| **Skill id（唯一真源）** | 各 `SKILL.md` frontmatter 的 `name:` |
| **文件路径** | `agents/<id>/skills/manifest.json` → `skills[].path` |
| **mode → skill** | 同 manifest 的 `mode_to_skill_id`（值必须等于某条 `SKILL.md` 的 `name`） |
| **禁止** | 在 manifest 里写 `id` 字段（加载时报错） |

注册时：

```python
from agent_platform.skills.bundle import with_skill_bundle

reg.register(
    with_skill_bundle(
        AgentDefinition(..., mcp_tool_names=[...]),
        bundle_key="my-agent",  # 与 pyproject entry_point 名一致
    )
)
```

运行期 overlay 走 `load_skill_overlay_for_mode`，且**必须**已激活 `AgentScope`；只用本 Agent 的 `skill_mode_map`，不用全局合并的 mode 表。

`RECAP_SKILL_EXTRA_DIRS` 仅向**全局 skill 目录**追加 id；要改变某 Agent 的 mode 映射请改其 bundle 或 `RECAP_SKILL_ID`（须在 `skills` 白名单内）。

### 4.3 Prompts

- 业务 system 底座：`agents/<id>/prompts/` 或 `resources/prompts/`（entry_point `agent_platform.prompts`）。
- 对话类 Agent 也可在 `prompts.py` 直接拼装，不必走 Skill bundle。

---

## 五、HTTP

1. 在 `agents/<id>/http_routes.py` 定义 `APIRouter`。
2. 在 manifest 的 `http_router_factories` 返回该 router 列表。
3. `interfaces/api/app.py` 的 `create_app()` 会遍历 `AgentRegistry` 自动 `include_router`。

鉴权与限流复用 `interfaces/api/deps.py` 的 `require_api_key` / `require_rate_limit`（全局 `RECAP_API_KEY`）。

---

## 六、CLI 交互模式

平台提供 `adapters/cli/repl.py` 的 `run_repl`。`hsk30-tutor` 与 `stock-recap` 默认进入 REPL；脚本单轮用 `--once` 或 `-m` + `--once`。

---

## 七、测试

| 类型 | 建议 |
|------|------|
| 单元 | `tests/test_<agent>_*.py`，mock LLM / 数据源 |
| CLI | 断言 `register_subparser` 参数；`--once` + mock 返回码 0 |
| HTTP | `TestClient` 调 `/v1/<prefix>/...` |

---

## 八、注意事项

1. **不要改 `core/`**，扩展用 Port 或新 infra 实现。
2. **Agent ID 用 kebab-case**（`my-agent`），Python 包名用下划线（`my_agent`）。
3. **配置**：复用 `RECAP_*` 全局项，或后续为专属 Agent 增加带前缀的 Settings 字段（避免与 recap 冲突）。
4. **第三方包**：wheel 里声明 `[project.entry-points."agent_platform.agents"]` 即可被 `discover_agents()` 加载，不必改本仓库 `factory.py`。

---

## 九、文件清单示例（`news-digest`）

```
新增：
  src/agent_platform/agents/news_digest/
    __init__.py
    models.py
    use_case.py
    manifest.py
    cli.py
    http_routes.py          # 可选
  tests/test_news_digest.py

修改：
  src/agent_platform/runtime/factory.py   # register_builtin_agents 一行
  pyproject.toml                            # 可选 entry_points
```

**不要**再创建 `interfaces/agents/`、`application/` 或修改 `AGENTS` 字典——这些路径已在 W16 删除。
