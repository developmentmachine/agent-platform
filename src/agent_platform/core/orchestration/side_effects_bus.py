"""SideEffectBus — 副作用事件总线（取代 ``application/side_effects`` 的函数集合）。

为什么需要总线：
- 现状各 Agent 想加「run 完成后推送」「持久化后回测」等动作，必须 import 别的
  Agent 的副作用函数；
- 用总线后，Agent 在注册阶段订阅自己关心的事件（同步 / 异步均可），
  平台核心不再认识具体业务动作；
- 多租户与多 Agent 场景下，handler 注册天然按 Agent 隔离。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, DefaultDict, Dict, List, Optional

from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext

logger = logging.getLogger("agent_platform.core.orchestration.side_effects_bus")


class StandardEvent(str, Enum):
    """平台标准事件名；各 Agent 可订阅这些事件或自定义事件名。"""

    PHASE_DONE = "run.phase_done"
    RUN_PERSISTED = "run.persisted"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


@dataclass
class SideEffectContext:
    """事件 handler 收到的最小上下文。"""

    run_ctx: RunContext
    principal: PrincipalContext
    payload: Dict[str, Any] = field(default_factory=dict)


SideEffectHandler = Callable[[SideEffectContext], None]


class SideEffectBus:
    """单进程事件总线（线程内同步派发；异步 defer 由外层 BackgroundTasks 接管）。"""

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[SideEffectHandler]] = defaultdict(list)

    def subscribe(self, event: str | StandardEvent, handler: SideEffectHandler) -> None:
        key = event.value if isinstance(event, StandardEvent) else str(event)
        self._handlers[key].append(handler)

    def emit(
        self,
        event: str | StandardEvent,
        ctx: SideEffectContext,
        *,
        swallow_errors: bool = True,
    ) -> None:
        key = event.value if isinstance(event, StandardEvent) else str(event)
        for handler in list(self._handlers.get(key, ())):
            try:
                handler(ctx)
            except Exception as exc:
                if not swallow_errors:
                    raise
                logger.warning(
                    "side_effect_handler_failed event=%s handler=%s error=%s",
                    key,
                    getattr(handler, "__name__", repr(handler)),
                    exc,
                )

    def list_handlers(self, event: Optional[str | StandardEvent] = None) -> Dict[str, List[str]]:
        """调试用：列出当前订阅情况。"""
        if event is not None:
            key = event.value if isinstance(event, StandardEvent) else str(event)
            return {key: [getattr(h, "__name__", repr(h)) for h in self._handlers.get(key, ())]}
        return {
            k: [getattr(h, "__name__", repr(h)) for h in v]
            for k, v in self._handlers.items()
        }


__all__ = [
    "SideEffectBus",
    "SideEffectContext",
    "SideEffectHandler",
    "StandardEvent",
]
