"""infra — Driven Adapters：实现 ``core.ports`` 的具体技术细节。

迁移策略（W1 当前 commit）：
- 旧路径 ``agent_platform.infrastructure.*`` **仍是真实源**；
- 本子包 ``agent_platform.infra.*`` 通过 re-export 提供「新规范路径」；
- 双路径**完全等价**：任意 import 都解析到同一模块对象；
- 后续 commit 物理迁移代码到本子包，旧路径转为 shim。

子模块：
- ``llm``         LLM 后端实现（openai / ollama / cursor-cli / gemini-cli）
- ``mcp_client``  MCP 客户端实现（stdio / http / router / pool） — **新代码**
- ``persistence`` SQLite / 仓储实现
- ``memory``      Qdrant / embeddings
- ``push``        企微等推送
- ``guardrail``   默认护栏与输出规则
"""
# 等价别名（运行时延迟绑定，避免循环导入）：
from agent_platform import infrastructure as _legacy

llm = _legacy.llm  # type: ignore[attr-defined]
persistence = _legacy.persistence  # type: ignore[attr-defined]
memory = _legacy.memory  # type: ignore[attr-defined]
push = _legacy.push  # type: ignore[attr-defined]

__all__ = ["llm", "persistence", "memory", "push"]
