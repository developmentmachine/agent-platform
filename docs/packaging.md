# 打包与发布指南

> Agent Platform 采用 **monolith 作为 source of truth + symlink 模式**构建独立 wheel 包。
> 业界同类方案：Google monorepo、Meta Buck、Turborepo。

---

## 1. 包结构总览

```
agent-platform/
├── src/agent_platform/          ← 唯一源码（monolith）
│   ├── core/                    ← agent-platform-core wheel
│   ├── infra/                   ← agent-platform-infra wheel
│   ├── agents/stock_recap/      ← agent-platform-stock-recap wheel
│   ├── agents/hsk30_tutor/      ← agent-platform-hsk30-tutor wheel
│   ├── adapters/                ← monolith only
│   ├── runtime/                 ← monolith only
│   └── tools_server/            ← monolith only
├── packages/
│   ├── core/
│   │   ├── pyproject.toml
│   │   └── src/agent_platform → symlink → ../../../src/agent_platform
│   ├── infra/
│   │   ├── pyproject.toml
│   │   └── src/agent_platform → symlink
│   ├── stock-recap/
│   │   ├── pyproject.toml
│   │   └── src/agent_platform → symlink
│   └── hsk30-tutor/
│       ├── pyproject.toml
│       └── src/agent_platform → symlink
├── pyproject.toml               ← monolith + uv workspace
└── dist/                        ← 构建产物
```

---

## 2. 包定义

### 2.1 core（零外部依赖）

```toml
# packages/core/pyproject.toml
[project]
name = "agent-platform-core"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []  # 零外部依赖

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = [
    "src/agent_platform/core",
    "src/agent_platform/domain",
    "src/agent_platform/config",
]
```

### 2.2 infra（依赖 core）

```toml
# packages/infra/pyproject.toml
[project]
name = "agent-platform-infra"
version = "0.1.0"
dependencies = [
    "agent-platform-core>=0.1.0",
    "openai>=1.40.0",
    "httpx>=0.27.0",
    "qdrant-client>=1.7.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = [
    "src/agent_platform/infra",
]
```

### 2.3 agent 包（stock-recap 示例）

```toml
# packages/stock-recap/pyproject.toml
[project]
name = "agent-platform-stock-recap"
version = "0.1.0"
dependencies = [
    "agent-platform-core>=0.1.0",
    "agent-platform-infra>=0.1.0",
    "akshare",
    "tenacity>=8.3.0",
]

[project.entry-points."agent_platform.agents"]
stock-recap = "agent_platform.agents.stock_recap.manifest:register"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = [
    "src/agent_platform/agents/stock_recap",
]
```

### 2.4 hsk30-tutor（最简 agent）

```toml
# packages/hsk30-tutor/pyproject.toml
[project]
name = "agent-platform-hsk30-tutor"
version = "0.1.0"
dependencies = [
    "agent-platform-core>=0.1.0",
    "agent-platform-infra>=0.1.0",
    "openai>=1.40.0",
]

[project.scripts]
hsk30-tutor = "agent_platform.agents.hsk30_tutor.cli:main"

[project.entry-points."agent_platform.agents"]
hsk30-tutor = "agent_platform.agents.hsk30_tutor.manifest:register"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = [
    "src/agent_platform/agents/hsk30_tutor",
]
```

---

## 3. 构建流程

### 3.1 全量构建

```bash
cd /opt/data/agent-platform

for pkg in core infra stock-recap hsk30-tutor; do
    echo "Building $pkg..."
    cd packages/$pkg
    uv build --no-cache
    cd ../..
done

ls -la dist/*.whl
```

### 3.2 单包构建

```bash
cd packages/core && uv build --no-cache
# → dist/agent_platform_core-0.1.0-py3-none-any.whl
```

### 3.3 验证 wheel 内容

```bash
python3 -c "
import zipfile
with zipfile.ZipFile('dist/agent_platform_core-0.1.0-py3-none-any.whl') as z:
    for name in z.namelist():
        print(name)
"
```

---

## 4. 独立安装验证

### 4.1 core 独立导入

```bash
python3 -m venv /tmp/test-core && source /tmp/test-core/bin/activate
pip install dist/agent_platform_core-0.1.0-py3-none-any.whl
python3 -c "
from agent_platform.core.ports.llm import LlmBackendPort
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.app import AgentApp
print('✅ core 独立导入成功')
"
```

### 4.2 agent 独立安装 + 自动发现

```bash
python3 -m venv /tmp/test-agent && source /tmp/test-agent/bin/activate
pip install dist/agent_platform_core-0.1.0-py3-none-any.whl
pip install dist/agent_platform_infra-0.1.0-py3-none-any.whl
pip install dist/agent_platform_stock_recap-0.1.0-py3-none-any.whl

python3 -c "
from importlib.metadata import entry_points
eps = entry_points(group='agent_platform.agents')
for ep in eps:
    print(f'✅ 发现 agent: {ep.name} → {ep.value}')
"
```

---

## 5. 新 Agent 打包

### 5.1 目录结构

```
packages/my-agent/
├── pyproject.toml
└── src/agent_platform → symlink → ../../../src/agent_platform
```

### 5.2 pyproject.toml 模板

```toml
[project]
name = "agent-platform-my-agent"
version = "0.1.0"
description = "My custom agent"
requires-python = ">=3.10"
dependencies = [
    "agent-platform-core>=0.1.0",
    "agent-platform-infra>=0.1.0",
    # 业务依赖
]

[project.entry-points."agent_platform.agents"]
my-agent = "agent_platform.agents.my_agent.manifest:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_platform"]
only-include = [
    "src/agent_platform/agents/my_agent",
]
```

### 5.3 创建 symlink + 构建

```bash
cd packages/my-agent
ln -s ../../../src/agent_platform src/agent_platform
uv build --no-cache
# → dist/agent_platform_my_agent-0.1.0-py3-none-any.whl
```

### 5.4 发布

```bash
# 内部 PyPI
uv publish --publish-url https://pypi.internal.company.com

# 公开 PyPI
uv publish
```

---

## 6. uv workspace 配置

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

workspace 内 `uv sync` 会自动解析本地包依赖，无需先发布到 PyPI。

---

## 7. CI/CD 集成

```yaml
# .github/workflows/build-packages.yml
name: Build Packages
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync

      - name: Run tests
        run: uv run pytest tests/ -q

      - name: Build all packages
        run: |
          for pkg in core infra stock-recap hsk30-tutor; do
            cd packages/$pkg && uv build --no-cache && cd ../..
          done

      - name: Verify independent imports
        run: |
          python3 -m venv /tmp/verify
          /tmp/verify/bin/pip install dist/agent_platform_core-*.whl
          /tmp/verify/bin/python -c "from agent_platform.core.app import AgentApp; print('OK')"

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: wheels
          path: dist/*.whl
```

---

## 8. 常见问题

### Q: 为什么用 symlink 而不是把源码复制到 packages/？

答：monolith 作为 source of truth 确保：
- 只有一份源码，不会出现 packages/ 和 src/ 不同步
- 测试始终跑 monolith 的代码
- wheel 构建时通过 `only-include` 过滤，只打包需要的文件

### Q: core 和 monolith 会冲突吗？

答：不会。两者共享 `agent_platform` 命名空间（namespace package，无 `__init__.py` 冲突）。安装 core wheel 后再 editable install monolith，Python 会合并两者的文件。

### Q: 如何只部署一个 agent？

答：
```bash
pip install agent-platform-core agent-platform-infra agent-platform-stock-recap
# 或通过 AgentApp 直接运行
```

### Q: 如何添加新的端口协议？

答：在 `core/ports/` 新建 Protocol 类，然后在 `infra/` 提供实现。agent 通过 `deps.py` 注入。
