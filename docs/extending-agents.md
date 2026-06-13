# 扩展新 Agent 指导手册

> **v2 平台化架构**：新 Agent 必须放在 `src/agent_platform/agents/<id>/`，通过 `AgentDefinition` + `manifest.register` 接入。
> 完整分层见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。打包指南见 [`packaging.md`](./packaging.md)。
> 内置示例：`stock-recap`、`hsk30-tutor`。

---

## 〇、TL;DR（最小新 Agent 5 步）

```
1) 新建 src/agent_platform/agents/<id>/（models · use_case · manifest.py）
2) 实现 runner（或 Pipeline[StateT] + Phase 子类）
3) manifest.py：reg.register(AgentDefinition(...))
4) pyproject.toml 声明 entry_points（自动发现，无需改 factory.py）
5) pytest + uv run lint-imports
```

**关键原则**：
- Agent 只依赖 `core.*`（端口协议），不直接 import `infra.*`
- infra 实现通过 `deps.py` DI 容器注入
- entry_points 自动发现 — 安装 wheel 后无需改任何平台文件

---

## 一、平台分层（你要动哪里）

| 层 | 路径 | 新 Agent 时 |
|----|------|-------------|
| `core/` | 端口协议、Pipeline、Registry、AgentApp | **不改** |
| `infra/` | LLM、DB、MCP client、Push、Guardrail | 一般不改 |
| `agents/<id>/` | 业务代码 + deps.py + manifest.py | ✅ 全部在这里 |
| `adapters/` | CLI / HTTP / QQ / 调度 | 一般不改 |

**Agent 之间禁止互相 import**（`import-linter` 强制）。
**Agent → infra 禁止模块级 import**（全部通过 DI / 函数内 lazy import）。

---

## 二、参考实现

| Agent | 目录 | 能力 | 要点 |
|-------|------|------|------|
| `stock-recap` | `agents/stock_recap/` | REPORT, STREAMING, SCHEDULED, TOOL_USING | Phase pipeline、skills、MCP、DI 容器（deps.py）、定时任务 |
| `hsk30-tutor` | `agents/hsk30_tutor/` | CHAT, STREAMING | 轻量 `chat_completion`、字词约束验证、自动重试修正、装饰器模式 |

阅读顺序：`manifest.py` → `deps.py`（如有）→ `use_case.py` → `cli.py` → `http_routes.py`。

> **hsk30-tutor 是纯业务 Agent 的最佳参考**：只依赖 `core.*` + `config.*`，不碰 `infra.*`。
> **stock-recap 是复杂 Agent 的参考**：DI 容器、Phase pipeline、MCP 工具、定时任务。

---

## 三、manifest 最小示例

### 3.1 纯对话 Agent（无 MCP / 无 Skill）

```python
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentResponseEnvelope,
)
from agent_platform.core.registry.agent_registry import AgentRegistry

AGENT_ID = "my-agent"


def _runner(*, envelope, principal, session, run_ctx, settings, runtime):
    # envelope.payload → 业务逻辑 → AgentResponseEnvelope
    req = MyRequest.model_validate(envelope.payload)
    # ... 业务逻辑 ...
    return AgentResponseEnvelope(
        agent_id=AGENT_ID,
        request_id=run_ctx.request_id,
        payload={"answer": answer},
    )


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
            mcp_tool_names=[],
            cli_help="一句话 help",
            http_path_prefix="/v1/my-agent",
            cli_subparser_factory=lambda sub: __import__(
                "agent_platform.agents.my_agent.cli", fromlist=["register_subparser"]
            ).register_subparser(sub),
            cli_run_handler=lambda args, s, p: __import__(
                "agent_platform.agents.my_agent.cli", fromlist=["run"]
            ).run(args, s, p),
            http_router_factories=[lambda: [__import__(
                "agent_platform.agents.my_agent.http_routes", fromlist=["router"]
            ).router]],
        )
    )
```

### 3.2 带 DI 容器的 Agent（stock-recap 模式）

当 Agent 需要访问 infra 实现（数据库、LLM、Push 等）时，**必须通过 DI 容器注入**：

```python
# agents/my_agent/deps.py — 依赖注入容器
from dataclasses import dataclass
from typing import Optional, Callable
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.ports.guardrail import GuardrailPort


@dataclass
class MyAgentDeps:
    repo_factory: RepositoryFactoryPort
    guardrail: GuardrailPort
    llm_caller: Optional[Callable] = None
    init_db: Optional[Callable[[str], None]] = None


_default: Optional[MyAgentDeps] = None


def configure_default_deps(*, repo_factory, guardrail, llm_caller=None, init_db=None):
    global _default
    _default = MyAgentDeps(
        repo_factory=repo_factory,
        guardrail=guardrail,
        llm_caller=llm_caller,
        init_db=init_db,
    )


def default_deps() -> MyAgentDeps:
    if _default is not None:
        return _default
    raise RuntimeError(
        "My agent deps not configured. "
        "Call configure_default_deps() from the bootstrap entry point."
    )


def reset_default_deps():
    global _default
    _default = None
```

```python
# agents/my_agent/use_case.py — 业务逻辑（只用端口，不用 infra）
from agent_platform.agents.my_agent.deps import default_deps


def do_something(req, settings):
    deps = default_deps()
    repo = deps.repo_factory.run_repository()
    # ... 业务逻辑 ...
    # LLM 调用通过注入的 llm_caller
    if deps.llm_caller:
        answer, tokens = deps.llm_caller(
            settings=settings, mode=req.mode, messages=messages,
        )
```

```python
# monolith bootstrap（CLI / HTTP 入口）— 只在这里 import infra
from agent_platform.agents.my_agent.deps import configure_default_deps
from agent_platform.infra.persistence.factory import SqliteRepositoryFactory
from agent_platform.infra.policy.guardrails import GuardrailAdapter
from agent_platform.infra.persistence.db import init_db
from agent_platform.infra.llm.backends import call_llm

configure_default_deps(
    repo_factory=SqliteRepositoryFactory(db_path),
    guardrail=GuardrailAdapter(),
    llm_caller=lambda **kw: call_llm(**kw),
    init_db=init_db,
)
```

**原则**：`infra.*` 的 import 只出现在 monolith bootstrap 入口，不出现在 agent 业务代码中。

---

## 四、依赖注入（DI）模式详解

### 4.1 端口协议（core/ports/）

Agent 通过端口协议与 infra 解耦：

| 端口 | 用途 | 位置 |
|------|------|------|
| `LlmBackendPort` | LLM 调用 | `core/ports/llm.py` |
| `RepositoryFactoryPort` | 数据库访问（6 个 repo） | `core/ports/repository.py` |
| `GuardrailPort` | 输入/输出护栏 | `core/ports/guardrail.py` |
| `PushPort` | 消息推送 | `core/ports/push.py` |
| `EmbeddingsPort` | 文本向量化 | `core/ports/memory.py` |
| `VectorStorePort` | 向量存储 | `core/ports/memory.py` |
| `MetricsPort` | 指标采集 | `core/ports/metrics.py` |
| `SessionResolverPort` | 会话解析 | `core/ports/session.py` |
| `RendererPort` | 内容渲染 | `core/ports/renderer.py` |
| `McpClientPort` | MCP 工具调用 | `core/ports/mcp_tool.py` |

### 4.2 注入方式

```python
# 方式一：deps 单例（stock-recap 模式）
deps = default_deps()
repo = deps.repo_factory.run_repository()

# 方式二：函数参数传递
def generate_once(req, settings, *, repo_factory=None, guardrail=None):
    rf = repo_factory or default_deps().repo_factory
    gr = guardrail or default_deps().guardrail

# 方式三：AgentApp（独立运行模式）
app = AgentApp(agent_id="my-agent", llm=my_llm, repo_factory=my_repo)
result = app.run(payload={...})
```

---

## 五、独立打包

### 5.1 创建包目录

```bash
mkdir -p packages/my-agent
cd packages/my-agent
ln -s ../../../src/agent_platform src/agent_platform
```

### 5.2 pyproject.toml

```toml
[project]
name = "agent-platform-my-agent"
version = "0.1.0"
dependencies = [
    "agent-platform-core>=0.1.0",
    "agent-platform-infra>=0.1.0",
]

[project.entry-points."agent_platform.agents"]
my-agent = "agent_platform.agents.my_agent.manifest:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = ["src/agent_platform/agents/my_agent"]
```

### 5.3 构建 + 验证

```bash
uv build --no-cache
# → dist/agent_platform_my_agent-0.1.0-py3-none-any.whl

# 验证 entry_points
python3 -c "
import zipfile
with zipfile.ZipFile('dist/agent_platform_my_agent-0.1.0-py3-none-any.whl') as z:
    for name in z.namelist():
        if 'entry_points' in name:
            print(z.read(name).decode())
"
# 应输出:
# [agent_platform.agents]
# my-agent = agent_platform.agents.my_agent.manifest:register
```

### 5.4 独立安装

```bash
pip install agent-platform-core agent-platform-infra
pip install dist/agent_platform_my_agent-0.1.0-py3-none-any.whl

# 自动发现
python3 -c "
from importlib.metadata import entry_points
eps = entry_points(group='agent_platform.agents')
for ep in eps:
    print(f'{ep.name} → {ep.value}')
"
```

详细打包流程见 [`docs/packaging.md`](./packaging.md)。

---

## 六、带 MCP + Skill bundle 的 Agent

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

注册 entry_points：

```toml
[project.entry-points."agent_platform.agents"]
my-agent = "agent_platform.agents.my_agent.manifest:register"

[project.entry-points."agent_platform.skills"]
my-agent = "agent_platform.agents.my_agent.skills:bundle_root"
```

---

## 七、HTTP / CLI / Scheduler

### 7.1 HTTP

1. 在 `agents/<id>/http_routes.py` 定义 `APIRouter`。
2. 在 manifest 的 `http_router_factories` 返回该 router 列表。
3. `adapters/http/app.py` 的 `create_app()` 会遍历 `AgentRegistry` 自动 `include_router`。

鉴权复用 `core/http.py` 的 `require_api_key`。

### 7.2 CLI

在 manifest 声明 `cli_subparser_factory` + `cli_run_handler`，CLI 子命令自动出现。

### 7.3 Scheduler

在 manifest 声明 `scheduled_jobs`，`adapters/scheduler/` 自动发现。

---

## 八、测试

| 类型 | 建议 |
|------|------|
| 单元 | `tests/test_<agent>_*.py`，mock LLM / 数据源 |
| DI 测试 | 用 `configure_default_deps` + `reset_default_deps` fixture |
| CLI | 断言 `register_subparser` 参数；`--once` + mock 返回码 0 |
| HTTP | `TestClient` 调 `/v1/<prefix>/...` |
| 覆盖率 | `pytest --cov=agent_platform.agents.<id>` — hsk30-tutor 达 91% |

测试中配置 DI：

```python
from agent_platform.agents.my_agent.deps import configure_default_deps, reset_default_deps

@pytest.fixture(autouse=True)
def _wire_deps(tmp_path):
    rf = SqliteRepositoryFactory(str(tmp_path / "test.db"))
    configure_default_deps(repo_factory=rf, guardrail=NoopGuardrail())
    yield
    reset_default_deps()
```

---

## 九、注意事项

1. **不要改 `core/`**，扩展用 Port 或新 infra 实现。
2. **Agent ID 用 kebab-case**（`my-agent`），Python 包名用下划线（`my_agent`）。
3. **不要直接 import `infra.*`** — 通过 `deps.py` DI 注入。
4. **entry_points 是唯一注册方式** — 不要修改 `runtime/factory.py` 的硬编码列表。
5. **Agent 间禁止互引** — `import-linter` 强制。
6. **配置**：复用全局 `Settings`，或为专属 Agent 增加带前缀的字段。

---

## 十、文件清单示例

### 10.1 纯对话 Agent（hsk30-tutor 模式）

```
新增：
  src/agent_platform/agents/my_agent/
    __init__.py          ← AGENT_ID 常量
    models.py            ← Pydantic 请求/响应模型
    use_case.py          ← 业务编排（@_with_agent_scope 装饰器）
    manifest.py          ← AgentDefinition 注册（lambda 懒加载 CLI/HTTP）
    http_routes.py       ← FastAPI APIRouter
    cli.py               ← CLI 子命令
  packages/my-agent/
    pyproject.toml       ← wheel 配置 + entry_points
    src/agent_platform → symlink

修改：
  无（entry_points 自动发现）
```

### 10.2 带 DI 的复杂 Agent（stock-recap 模式）

```
新增：
  src/agent_platform/agents/my_agent/
    __init__.py
    models.py
    deps.py              ← DI 容器（configure_default_deps / default_deps）
    use_case.py          ← 业务逻辑（通过 deps 获取端口）
    manifest.py          ← 注册 + CLI/HTTP/Scheduler 钩子
    http_routes.py
    cli.py
    phases/              ← Phase 子类（可选）
    effects/             ← 副作用处理（可选）
    data/                ← 数据采集（可选）
  packages/my-agent/
    pyproject.toml
    src/agent_platform → symlink

修改：
  无（entry_points 自动发现）
```
