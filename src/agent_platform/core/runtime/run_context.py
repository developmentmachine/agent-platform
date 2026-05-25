"""``RunContext`` 的新规范位置 — 直接 re-export 老实现，保 100% 兼容。

物理迁移在后续 commit 完成；目前 import 路径双通：
- 旧：``from agent_platform.domain.run_context import RunContext``
- 新：``from agent_platform.core.runtime import RunContext``
"""
from agent_platform.domain.run_context import RunContext  # noqa: F401

__all__ = ["RunContext"]
