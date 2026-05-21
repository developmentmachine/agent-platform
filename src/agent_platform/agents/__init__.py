"""内置 Agent 包 — 每个 Agent 一个子目录，互相隔离。

边界规则（import-linter 强制）：
- ``agents.<a>`` 与 ``agents.<b>`` 不得互相 import；
- ``agents.<x>`` 只能依赖 ``core.*`` / ``infra.*``（通过 ports）；
- 平台层 ``core`` / ``runtime`` / ``adapters`` 禁止 import 任何 ``agents.*``
  （Agent 通过 ``AgentRegistry`` 注入）。

每个 Agent 必须提供 ``manifest.py``，导出 ``register(registry)`` 函数。
"""
