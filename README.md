# Agent Platform 使用文档

**Agent Platform** 是多智能体运行平台：统一 CLI / HTTP / 调度 / QQ·企微等入口，通过 `AgentRegistry` 自动发现各业务 Agent。当前内置：

| Agent ID | 说明 | 能力 |
|----------|------|------|
| `stock-recap` | A 股日终复盘 / 次日策略 | 报告、流式 NDJSON、定时任务、MCP 工具 |
| `hsk30-tutor` | HSK 3.0 中文对话陪练（新三阶段九级，非 HSK 2.0） | 多轮对话（CHAT） |

平台架构与扩展方式见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs/extending-agents.md](docs/extending-agents.md)。`stock-recap` 业务设计见 [docs/ARCHITECTURE_AND_BUSINESS.md](docs/ARCHITECTURE_AND_BUSINESS.md)。

---

## 一、本地运行

### 环境准备

```bash
git clone <repo-url>
cd agent-platform   # 以实际仓库目录名为准

pip install uv
uv sync
```

复制配置：

```bash
cp .env.example .env
```

编辑 `.env`，至少配置 LLM 后端（见第三节）。`hsk30-tutor` 默认使用 OpenAI 兼容接口（`OPENAI_API_KEY` + `RECAP_MODEL`）；未配置 API Key 时返回本地占位回复。

---

### 命令格式

```
uv run agent-platform <agent-id> [参数]
```

查看已注册 Agent 与能力：

```bash
uv run agent-platform --help
uv run agent-platform --list-agents
uv run agent-platform stock-recap --help
uv run agent-platform hsk30-tutor --help
```

> **免 `uv run` 前缀**：`uv tool install --editable .` 后可直接使用 `agent-platform <agent-id> ...`。

### 架构检查（CI 同款）

```bash
uv run lint-imports
```

`stock-recap` 默认走 **pipeline v2**（`RECAP_PIPELINE_V2=true`，Phase 编排）。排障对比旧路径：

```bash
RECAP_PIPELINE_V2=false uv run agent-platform stock-recap --once --mode daily --provider mock --no-llm
```

---

### stock-recap：快速测试（无需 API Key）

```bash
# mock 数据，不调用 LLM
uv run agent-platform stock-recap --once --mode daily --provider mock --no-llm

# 查看将发给 LLM 的 payload
uv run agent-platform stock-recap --once --mode daily --provider mock --dry-run
```

**交互 REPL（默认）**：不带 `--once` / `--serve` 等独占动作时进入交互模式，可用 `run daily`、`set provider mock`、`history` 等命令。

```bash
uv run agent-platform stock-recap --provider mock
```

---

### stock-recap：生成复盘

```bash
# 单轮：日终复盘（真实行情）
uv run agent-platform stock-recap --once --mode daily --provider live --model cursor-cli

# 单轮：次日策略
uv run agent-platform stock-recap --once --mode strategy --provider live --model cursor-cli

# 指定日期
uv run agent-platform stock-recap --once --mode daily --provider live --date 2024-01-02

# 仅 stdout，不写文件
uv run agent-platform stock-recap --once --mode daily --provider mock --no-write-files
```

`--provider` 常用值：`mock`（离线测试）、`live`（多源 fallback）、`akshare`（显式 AkShare）。可用 `agent-platform stock-recap --help` 查看注册表中的全部 id。

---

### hsk30-tutor：中文陪练

```bash
# 交互 REPL（默认）
uv run agent-platform hsk30-tutor
uv run agent-platform hsk30-tutor --level 3 --locale zh

# 单轮脚本
uv run agent-platform hsk30-tutor -m "请纠正：我昨天去了商店。" --once
uv run agent-platform hsk30-tutor -m "你好" --once --json
```

REPL 内命令：`/level 1-9`、`/locale zh|en|both`、`/clear`、`/help`、`/quit`。

需配置 `OPENAI_API_KEY`（及可选 `RECAP_MODEL`）方可调用真实 LLM；否则为 stub 占位回复。

考纲数据占位目录：`src/agent_platform/resources/hsk30/`（见该目录 README）。

---

### 启动 API 服务

`stock-recap --serve` 会启动统一 FastAPI 应用，并**自动挂载所有已注册 Agent 的 HTTP 路由**（含 `hsk30-tutor`）。

```bash
uv run agent-platform stock-recap --serve --host 0.0.0.0 --port 8000

# 带调度器（交易日 15:30 / 15:35 / 15:40 自动任务，仅 stock-recap）
RECAP_SCHEDULER_ENABLED=true uv run agent-platform stock-recap --serve
```

文档：http://localhost:8000/docs

| 路径 | Agent | 说明 |
|------|-------|------|
| `POST /v1/recap` | stock-recap | 生成复盘 JSON |
| `POST /v1/recap/stream` | stock-recap | NDJSON 阶段流 |
| `GET /v1/history` 等 | stock-recap | 历史、反馈等 |
| `POST /v1/hsk30-tutor/chat` | hsk30-tutor | 多轮陪练（body 含 `message`、`level`、`history`） |

鉴权：设置 `RECAP_API_KEY` 后，上述 `/v1/*` 需 `X-API-Key`（与 recap 相同）。

---

### QQ 机器人

在 `.env` 中配置（见 `.env.example` 中 `QQ_BOT_*` 段）：

```bash
QQ_BOT_ENABLED=true
QQ_BOT_APP_ID=你的AppID
QQ_BOT_CLIENT_SECRET=你的ClientSecret
QQ_BOT_RECAP_PROVIDER=live
QQ_BOT_RECAP_FORCE_LLM=true
# QQ_DEFAULT_AGENT_ID=stock-recap
```

启动长连接：

```bash
uv run agent-platform-qq-bot
```

使用方式：

- **QQ 群**：@ 机器人后发消息（默认 `stock-recap` 日终复盘；含「策略」「明天」走次日策略）
- **私聊**：直接发文字

单次复盘可能耗时 1～2 分钟；事件在线程池执行，不阻塞心跳。**长回复**会按段落拆成多条消息发送（被动回复最多 5 条，超出改主动消息），避免在 adapter 层硬截断。

---

### stock-recap：其它命令

```bash
uv run agent-platform stock-recap --history --limit 20
uv run agent-platform stock-recap --evolve
uv run agent-platform stock-recap --backtest
RECAP_WXWORK_WEBHOOK_URL=https://... uv run agent-platform stock-recap --push-test
```

---

### 数据库

默认：`recap_system.db`（WAL，跨进程安全）。

```bash
RECAP_DB_PATH=./data/recap.db uv run agent-platform stock-recap --once --mode daily --provider mock
RECAP_DB_PATH=:memory: uv run agent-platform stock-recap --once --mode daily --provider mock
```

---

## 二、容器部署

一次性启动（推荐）：

```bash
cp .env.docker.example .env
# 编辑 .env：至少按需填写 OPENAI_API_KEY、RECAP_API_KEY、RECAP_SCHEDULER_ENABLED 等

docker compose up -d --build
docker compose ps
curl http://localhost:8000/healthz
```

默认会将数据库与报告输出持久化到宿主机 `./data`：

- `RECAP_DOCKER_DB_PATH=/data/recap_system.db`
- `RECAP_DOCKER_OUTPUT_DIR=/data/reports`
- `RECAP_HTTP_PORT=8000` 可改宿主机端口，例如 `RECAP_HTTP_PORT=18000 docker compose up -d`

停止服务：

```bash
docker compose down
```

如果只想手动构建/运行镜像：

```bash
docker build -t agent-platform .
docker run -d -p 8000:8000 \
  -e RECAP_LLM_BACKEND=openai \
  -e OPENAI_API_KEY=sk-... \
  -e RECAP_DB_PATH=/data/recap.db \
  -v $(pwd)/data:/data \
  --name agent-platform \
  agent-platform
```

镜像默认命令：`agent-platform stock-recap --serve --host 0.0.0.0 --port 8000`（挂载全部 Agent HTTP 路由）。

健康检查：

```bash
curl http://localhost:8000/healthz
```

### GitHub 验证

可以靠 GitHub Actions 做部署前验证：本仓库的 CI 会在 PR / `master` / `main` 上执行 Python 测试、Docker 镜像构建、容器健康检查、`docker compose config` 和 compose 启动烟测。提交 PR 后只要 CI 全绿，就说明镜像和 compose 至少能完成构建并启动到 `/healthz` 可用。

---

## 三、集成到 AI 大模型

通过 `RECAP_LLM_BACKEND` 与 `RECAP_MODEL`（或 `--model`）选择后端。`stock-recap` 与平台级工具循环共用该配置；`hsk30-tutor` 当前为 OpenAI Chat Completions 轻量客户端（无 function calling）。

### OpenAI / 兼容接口

```bash
OPENAI_API_KEY=sk-...
RECAP_LLM_BACKEND=openai
RECAP_MODEL=gpt-4.1-mini
```

### Gemini CLI / Cursor CLI / Ollama

与先前版本相同，详见 `.env.example`。`--model` 表达式示例：`openai:gpt-4o`、`ollama:qwen2.5:14b`、`cursor-cli`、`gemini-cli`。

### MCP 工具（stock-recap）

```bash
RECAP_TOOLS_ENABLED=true
RECAP_TOOLS_WEB_SEARCH=true
RECAP_TOOLS_MARKET_DATA=true
RECAP_TOOLS_HISTORY=true
```

独立 MCP 进程：`uv run agent-platform --mcp-tools`（或 `uv run stock-recap-mcp` / `agent-platform-tools-mcp`）。

---

### API 示例（stock-recap）

```bash
curl -X POST http://localhost:8000/v1/recap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-recap-api-key" \
  -d '{"mode": "daily", "provider": "live"}'

curl -N -X POST http://localhost:8000/v1/recap/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-recap-api-key" \
  -d '{"mode": "daily", "provider": "mock", "force_llm": false}'
```

流式协议：首行 `event: meta`，随后 `event: phase`（perceive … reflect），末行 `event: result`；失败为 `event: error`。

### API 示例（hsk30-tutor）

```bash
curl -X POST http://localhost:8000/v1/hsk30-tutor/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-recap-api-key" \
  -d '{"message": "你好", "level": 2, "history": [], "explain_locale": "both"}'
```

可选请求头 **`X-Session-Id`**：写入遥测，便于关联（stock-recap 主路径仍为单次生成）。

前端 CORS：`RECAP_CORS_ORIGINS`（逗号分隔）。未设置 `RECAP_API_KEY` 时不鉴权（仅建议本地开发）。

---

## 四、扩展新 Agent

1. 在 `src/agent_platform/agents/<id>/` 实现业务与 `manifest.py`（`register(reg)`）。
2. 在 `runtime/factory.py` 的 `register_builtin_agents` 注册，和/或在 `pyproject.toml` 的 `[project.entry-points."agent_platform.agents"]` 声明。
3. 在 manifest 中提供 `cli_subparser_factory` / `cli_run_handler`，可选 `http_router_factories`、`scheduled_jobs`。

CLI / HTTP **无需再改平台分发器**。详见 [docs/extending-agents.md](docs/extending-agents.md)。
