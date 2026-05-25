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

```python
from agent_platform.core.registry.agent_definition import (
    AgentDefinition,
    AgentCapability,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
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
            cli_help="一句话 help",
            http_path_prefix="/v1/my-agent",
            cli_subparser_factory=_cli_subparser,  # agents/my_agent/cli.py
            cli_run_handler=_cli_run,
            http_router_factories=[lambda: [my_router]],
        )
    )
```

注册后验证：

```bash
uv run agent-platform --list-agents
uv run agent-platform my-agent --help
```

---

## 四、Skills / Prompts（stock-recap 模式）

- Skill 放在 **`agents/stock_recap/skills/<name>/SKILL.md`**，由 entry_point `agent_platform.skills` 或包内 manifest 发现。
- System prompt 放在 **`agents/stock_recap/prompts/`** 或 `resources/prompts/`，entry_point `agent_platform.prompts`。

对话类 Agent（如 `hsk30-tutor`）可在包内 `prompts.py` 直接拼装 system 文本，不必走 Skill manifest。

---

## 五、HTTP

1. 在 `agents/<id>/http_routes.py` 定义 `APIRouter`。
2. 在 manifest 的 `http_router_factories` 返回该 router 列表。
3. `adapters/http/api/app.py` 的 `create_app()` 会遍历 `AgentRegistry` 自动 `include_router`。

鉴权与限流复用 `adapters/http/api/deps.py` 的 `require_api_key` / `require_rate_limit`（全局 `RECAP_API_KEY`）。

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
