"""平台级副作用：outbox 与延后任务组合（Composition Root 层）。"""
import agent_platform.runtime.side_effects.outbox as outbox
from agent_platform.runtime.side_effects.deferred import run_deferred_post_recap

__all__ = ["outbox", "run_deferred_post_recap"]
