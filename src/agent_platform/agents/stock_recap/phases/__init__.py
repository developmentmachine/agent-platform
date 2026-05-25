"""stock-recap 的 Phase 类化集合（W4）。

每个类是对现有 ``application.orchestration.pipeline._phase_*`` 函数的薄包装，
保留行为不变，但让 phase 拥有清晰的类型名、可单独测试 / mock、可与
``core.orchestration.Pipeline`` 直接组合。

W3 物理迁移后，这些类将不再依赖 ``application.orchestration.pipeline``，
而是直接把业务实现搬进各自类文件里。
"""
from agent_platform.agents.stock_recap.phases.act import ActPhase
from agent_platform.agents.stock_recap.phases.base import RecapPhase
from agent_platform.agents.stock_recap.phases.critique import CritiquePhase
from agent_platform.agents.stock_recap.phases.index_memory import IndexMemoryPhase
from agent_platform.agents.stock_recap.phases.perceive import PerceivePhase
from agent_platform.agents.stock_recap.phases.persist import PersistPhase
from agent_platform.agents.stock_recap.phases.plan import PlanPhase
from agent_platform.agents.stock_recap.phases.recall import RecallPhase
from agent_platform.agents.stock_recap.phases.reflect import ReflectPhase


def build_default_phases() -> list[RecapPhase]:
    """与现有 ``_PHASE_ORDER`` 顺序一致的默认 phase 列表。"""
    return [
        PerceivePhase(),
        RecallPhase(),
        PlanPhase(),
        ActPhase(),
        CritiquePhase(),
        PersistPhase(),
        IndexMemoryPhase(),
        ReflectPhase(),
    ]


__all__ = [
    "RecapPhase",
    "PerceivePhase",
    "RecallPhase",
    "PlanPhase",
    "ActPhase",
    "CritiquePhase",
    "PersistPhase",
    "IndexMemoryPhase",
    "ReflectPhase",
    "build_default_phases",
]
