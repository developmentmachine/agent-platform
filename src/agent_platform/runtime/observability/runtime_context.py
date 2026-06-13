"""ContextVar：在 tool / llm 等调用栈中读取当前 RunContext 与 Budget。

实际定义已迁移至 ``core.runtime.contextvars``，此处仅 re-export 保兼容。

为什么用 ContextVar 而不是参数下穿：
- ``LlmProvider.call`` 由注册表分发，强行加 budget 参数会污染所有实现。
- 工具执行链（``RecapToolRunner.execute`` → registry handler）已经较深，
  逐层透传 budget 难维护。
- ContextVar 只在「同一线程的同一调用栈」内可见，stream 路径下也成立
  （phase 函数在迭代器线程内同步执行）。
"""
from agent_platform.core.runtime.contextvars import (  # noqa: F401
    current_budget,
    current_run_context,
)
