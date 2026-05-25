# Agent Platform

通用智能体运行平台；内置业务 Agent **`stock-recap`**（A 股日终复盘 / 次日策略）。

- 平台 CLI：`agent_platform`（`pyproject.toml` → `agent_platform.interfaces.cli:cli_main`）
- 内置 Agent 注册：`[project.entry-points."agent_platform.agents"]` + `runtime.discover_agents`
- 架构与扩展：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)、[`docs/extending-agents.md`](docs/extending-agents.md)

---

## 环境准备

```bash
git clone <repo-url>
cd agent-platform

pip install uv
uv sync
cp .env.example .env
```

- **Python**：`>=3.10`（`pyproject.toml`）；CI / Docker 使用 **3.11**，本地建议与之对齐。
- 配置：工作目录下的 `.env`，环境变量前缀以 **`RECAP_`** 为主（见 `.env.example`）。

可选：将平台装为全局命令（editable，改代码即生效）：

```bash
uv tool install --editable .
agent_platform --list-agents
```

---

## CLI 用法

```text
agent_platform [--list-agents] [--mcp-tools]
agent_platform <agent-id> [agent 专属参数]
```

| 子命令 / 选项 | 说明 |
|---------------|------|
| `--list-agents` | 列出已注册 Agent（内置 + `entry_points`） |
| `--mcp-tools` | 启动 MCP stdio 工具服务（见下文「MCP 工具」） |
| `stock-recap` | 当前唯一内置业务 Agent |

```bash
uv run agent_platform --help
uv run agent_platform stock-recap --help
```

### stock-recap 常用示例

```bash
# mock 行情，不调用 LLM
uv run agent_platform stock-recap --mode daily --provider mock --no-llm

# mock + 查看将发给 LLM 的 payload
uv run agent_platform stock-recap --mode daily --provider mock --dry-run

# 日终复盘（真实行情）
uv run agent_platform stock-recap --mode daily --provider live --model cursor-cli

# 次日策略
uv run agent_platform stock-recap --mode strategy --provider live --model openai:gpt-4.1-mini

# 指定交易日
uv run agent_platform stock-recap --mode daily --provider live --date 2024-01-02

# 仅 stdout，不写 Markdown 文件
uv run agent_platform stock-recap --mode daily --provider mock --no-write-files
```

**互斥动作**（一次只能选一个）：`--serve` · `--dry-run` · `--evolve` · `--backtest` · `--push-test` · `--history`

```bash
# 启动 HTTP API（默认 127.0.0.1:8000）
uv run agent_platform stock-recap --serve --host 0.0.0.0 --port 8000

# 带内置调度器（需 RECAP_SCHEDULER_ENABLED=true）
RECAP_SCHEDULER_ENABLED=true uv run agent_platform stock-recap --serve

# 运维类
uv run agent_platform stock-recap --history --limit 20
uv run agent_platform stock-recap --evolve
uv run agent_platform stock-recap --backtest
RECAP_WXWORK_WEBHOOK_URL=https://... uv run agent_platform stock-recap --push-test
```

### 行情数据源 `--provider`

由 `DataProviderRegistry` 注册，内置 id：

| id | 说明 |
|----|------|
| `mock` | 确定性随机数据（按日期 seed），离线 / 自测 |
| `live` | 关键指数走东方财富 push2，其余 AkShare |
| `akshare` | 全量 AkShare |

可通过 `register_data_provider` 扩展自定义 id（见 `agents/stock_recap/data/collector.py`）。

### 数据库

默认 SQLite：`recap_system.db`（`RECAP_DB_PATH`，WAL，多进程可用）。

```bash
RECAP_DB_PATH=./data/recap.db uv run agent_platform stock-recap --mode daily --provider mock
# 仅单进程测试；多 worker 勿用
RECAP_DB_PATH=:memory: uv run agent_platform stock-recap --mode daily --provider mock
```

---

## HTTP API

`stock-recap --serve` 启动 FastAPI（`interfaces/api`）。文档：**http://localhost:8000/docs**

鉴权：设置 `RECAP_API_KEY` 后，`/v1/*` 需请求头 `X-API-Key`；未设置则不鉴权（仅建议本地开发）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 健康检查 |
| GET | `/metrics` | 业务指标 JSON |
| GET | `/metrics/prom` | Prometheus 文本格式 |
| GET | `/v1/history` | 运行历史 |
| POST | `/v1/recap` | 同步生成复盘 |
| POST | `/v1/recap/stream` | NDJSON 流式（`meta` → 各 `phase` → `result` / `error`） |
| POST | `/v1/feedback` | 用户反馈（驱动进化） |
| GET | `/v1/backtest` | 回测记录 |
| GET | `/v1/evolution` | 进化版本历史 |
| GET | `/v1/audit`、`/v1/audit/{request_id}` | 生成审计（需 `RECAP_AUDIT_ENABLED`） |
| POST/GET | `/v1/jobs`、`/v1/jobs/{job_id}` | 异步任务（长耗时生成） |
| POST/GET | `/v1/experiments` | Prompt 实验 |

流式复盘阶段名（与 pipeline 一致）：`perceive` → `recall` → `plan` → `act` → `critique` → `persist` → `index_memory` → `reflect`。

```bash
curl http://localhost:8000/healthz

curl -X POST http://localhost:8000/v1/recap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"mode": "daily", "provider": "live"}'

curl -N -X POST http://localhost:8000/v1/recap/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "X-Session-Id: optional-session" \
  -d '{"mode": "daily", "provider": "mock", "force_llm": false}'
```

跨域：设置 `RECAP_CORS_ORIGINS`（逗号分隔 Origin）后自动挂载 CORS。

---

## LLM 后端

由 `RECAP_LLM_BACKEND` 与 `RECAP_MODEL`（及 CLI `--model`）控制。`--model` 表达式：

| 表达式 | 后端 |
|--------|------|
| `openai:gpt-4o` | OpenAI API（需 `OPENAI_API_KEY`） |
| `ollama:qwen2.5:14b` | 本地 Ollama（`RECAP_OLLAMA_BASE_URL`） |
| `cursor-cli` | Cursor CLI（终端命令默认 `agent`，`RECAP_CURSOR_CLI_CMD`） |
| `gemini-cli` | Gemini CLI（`RECAP_GEMINI_CLI_CMD`，默认 `gemini`） |

兼容别名：`cursor-agent` / `RECAP_CURSOR_AGENT_CMD` / `RECAP_LLM_BACKEND=cursor-agent`。

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
export RECAP_LLM_BACKEND=openai
export RECAP_MODEL=gpt-4.1-mini

# Ollama
ollama pull qwen2.5:14b
export RECAP_LLM_BACKEND=ollama
export RECAP_MODEL=qwen2.5:14b

# Cursor CLI — https://cursor.com/docs/cli/overview
export RECAP_LLM_BACKEND=cursor-cli
export RECAP_CURSOR_CLI_CMD=agent

# Gemini CLI
export RECAP_LLM_BACKEND=gemini-cli
export GEMINI_API_KEY=...   # 可选，已登录时可省略
```

进程内工具（function calling / CLI 预取注入）：

```bash
RECAP_TOOLS_ENABLED=true
RECAP_TOOLS_WEB_SEARCH=true
RECAP_TOOLS_MARKET_DATA=true
RECAP_TOOLS_HISTORY=true
```

---

## MCP 工具服务

与进程内 `RECAP_TOOLS_*` 语义一致，可单独给外部 MCP Host 使用：

| 入口 | 说明 |
|------|------|
| `uv run agent_platform --mcp-tools` | 平台 CLI 全局开关 |
| `stock-recap-mcp` | 兼容旧脚本名（shim → `tools_server`） |
| `agent_platform-tools-mcp` | 独立 MCP server 进程 |

---

## 向量记忆（可选）

配置 Qdrant + OpenAI Embedding 后，长记忆写入 / 召回才会启用：

```bash
RECAP_QDRANT_URL=http://127.0.0.1:6333
OPENAI_API_KEY=sk-...          # 嵌入模型默认 text-embedding-3-small
RECAP_QDRANT_COLLECTION=agent_platform_memory
```

未配置 `RECAP_QDRANT_URL` 或 `OPENAI_API_KEY` 时自动跳过向量步骤。

---

## 容器部署

```bash
docker build -t stock-recap .
docker run -d -p 8000:8000 \
  -e RECAP_LLM_BACKEND=openai \
  -e OPENAI_API_KEY=sk-... \
  -e RECAP_DB_PATH=/data/recap.db \
  -v $(pwd)/data:/data \
  --name recap stock-recap
```

镜像默认 `CMD`：`agent_platform stock-recap --serve --host 0.0.0.0 --port 8000`；默认 `RECAP_DB_PATH=:memory:`，生产请挂卷。

**docker-compose**（推荐）：

```bash
# .env 中配置 OPENAI_API_KEY、RECAP_API_KEY、RECAP_SCHEDULER_ENABLED 等
docker compose up -d
docker compose logs -f
```

`docker-compose.yml` 已将 `./data` 挂载到 `/data`，与 `RECAP_DB_PATH=/data/recap_system.db` 默认值配合。

---

## 开发与 CI

```bash
# 测试
uv run pytest tests/ -v

# 架构边界（与 CI 相同）
uv run lint-imports
```

WeCom / QQ Bot 适配器位于 `adapters/wecom`、`adapters/qq`，通过 `AgentRuntime` 调用已注册 Agent；完整长连接接入为渐进式能力，部署前请阅读对应 connector 与环境变量。

新增 Agent：见 [`docs/extending-agents.md`](docs/extending-agents.md)（`agents/<id>/manifest.py` + `entry_points`，无需改平台 CLI 分发器）。

---

## 推送与调度

```bash
RECAP_PUSH_ENABLED=true
RECAP_WXWORK_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...

RECAP_SCHEDULER_ENABLED=true
RECAP_SCHEDULER_DAILY_HOUR=15
RECAP_SCHEDULER_DAILY_MINUTE=30
```

调度器在 `--serve` 且 `RECAP_SCHEDULER_ENABLED=true` 时由 `interfaces/scheduler/jobs` 启动，可触发日终复盘、次日策略与回测等 manifest 声明的 `scheduled_jobs`。
