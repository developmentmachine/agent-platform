"""stock-recap Agent — A 股日终复盘 / 次日策略智能体。

本目录是 stock-recap 的「业务包装层」：
- ``manifest.py``        注册到 AgentRegistry；
- 业务实现             仍位于历史路径（``application/recap.py`` 等），
                       本包暂以适配层方式驱动；后续 commit 中将物理迁入此处。

新 Agent 请参考此包结构与 ``docs/extending-agents.md``。
"""
from agent_platform.agents.stock_recap.manifest import register, AGENT_ID

__all__ = ["register", "AGENT_ID"]
