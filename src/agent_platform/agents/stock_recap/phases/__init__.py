"""stock-recap 的 Phase 类化集合（W4）。

各阶段业务实现在 ``phases/<name>.py`` 的 ``run(state, tracer)`` 中；
``RecapPhase`` 子类供 ``pipeline_v2`` 与单测使用。编排（预算/NDJSON）
在 ``legacy_pipeline``。
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
