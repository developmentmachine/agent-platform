# ADR-001：v2 平台化重构

- 状态：Accepted（refactor/v2-platform 分支）
- 日期：2026-05-21

## 背景

仓库始于「单一 stock-recap 智能体」，目标已演进为「通用 Agent Platform」。
原 4 层（domain / application / infrastructure / interfaces）虽规范，但：

- Orchestration 与 recap 业务强耦合，加第二个 Agent 必复制粘贴 pipeline；
- 工具栈有两套真实来源（本地 function-calling 注册表 + MCP stdio 镜像），双写；
- CLI / HTTP / Scheduler 都硬编码 AGENTS 字典或路由表，加入口要改三处；
- 没有跨入口统一的 Principal / Session 抽象，无法接 WeCom / QQ 等 bot。

## 决策

引入六层逻辑分层 + 三类物理包：

| 层 | 物理位置 | 角色 |
|----|----------|------|
| Application（驱动适配器） | `adapters/{cli,http,wecom,qq,scheduler,mcp_stdio}/` | 协议、鉴权、消息归一化 |
| Runtime | `runtime/` | Composition Root + 生命周期 |
| Orchestration | `core/orchestration/` | 泛型 Phase/Pipeline/Bus/Stream |
| Agents | `agents/<id>/` | 业务用例（互相隔离） |
| Core / Ports | `core/{ports,runtime,registry,errors}/` | 跨 Agent 抽象 |
| Infrastructure | `infra/` + 独立 `tools_server/` | Port 实现；工具 MCP-only |

并通过 **import-linter** 强制依赖方向（`pyproject.toml [tool.importlinter]`）。

## 兼容性

W1 commit 采用 **additive + shim** 策略：
- 新顶层包是规范路径；
- 老 4 层路径（`infrastructure/` 等）作为真实代码所在保留；
- 两套路径在 import 层完全等价；
- 全部 240 个原有测试不动；新增 20 个测试覆盖新抽象。

W2–W7 在同分支继续 commit，逐步物理迁移，最终删除老路径。

## 替代方案与放弃理由

| 方案 | 放弃理由 |
|------|----------|
| **uv workspace 多包**（ap-core / ap-runtime / ap-infra / ...） | Python 单仓多包工具成本高；同等效果可由 import-linter 达成；后期某 Agent 需独立发布时再拆 |
| 一次性物理迁移 127 个文件 | 测试网薄弱时风险高；W1 additive 策略保证零回归，后续 commit 可机械化迁移 |
| 全部沿用 4 层 | 第二个 Agent 必复制 pipeline；无法满足平台化目标 |

## 验证

- 260 个测试全过（原 240 + 新 20）；
- import-linter 4 个 contract 全部 KEPT；
- `create_runtime()` 装配链路实测可达，stock-recap 被注册到 AgentRegistry；
- WeCom / QQ adapter 骨架的归一化函数已具单测覆盖。

## 后果

- 第二个 Agent 接入：新建 `agents/<id>/manifest.py` 一行 register；
- 新 LLM / Tool / Memory 后端：实现对应 Port 即可；
- 入口扩展：在 `adapters/<x>/` 加 connector，统一调 `runtime.run(...)`；
- 平台代码长期维护人有了清晰的边界守护（CI 阻断违规）。
