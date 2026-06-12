"""HSK 3.0 考纲数据（2026-07 实施版）。

来源：《中文水平考试 HSK 考试大纲》中外语言交流合作中心 2025-11 发布。
包含：任务大纲、语法大纲、话题大纲、词汇表、认读字表、书写字表。

重构要点：
- _syllabus_field 装饰器消除 5 个结构相同的 getter 函数
- LevelSyllabus dataclass 保持不可变（frozen=True）
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Callable, Dict, FrozenSet, Tuple, TypeVar

from agent_platform.agents import hsk30_tutor as _pkg

T = TypeVar("T")


@dataclass(frozen=True)
class LevelSyllabus:
    """单个等级的考纲数据。"""
    level: int
    stage: str              # 初等 / 中等 / 高等
    band: str               # e.g. "Level 1", "Level 7–9"
    tasks: str              # 任务大纲原文
    grammar: str            # 语法大纲原文
    topics: str = ""        # 话题大纲原文
    vocabulary: FrozenSet[str] = frozenset()  # 累积词汇集
    char_recognition: frozenset = frozenset()  # 累积认读字
    char_writing: frozenset = frozenset()      # 累积书写字


_STAGE_MAP = {
    1: ("初等", "Level 1"), 2: ("初等", "Level 2"), 3: ("初等", "Level 3"),
    4: ("中等", "Level 4"), 5: ("中等", "Level 5"), 6: ("中等", "Level 6"),
    7: ("高等", "Level 7–9"), 8: ("高等", "Level 7–9"), 9: ("高等", "Level 7–9"),
}


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    ref = resources.files(_pkg).joinpath("syllabus_data.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _build_syllabus() -> Dict[int, LevelSyllabus]:
    raw = _load_raw()
    result: Dict[int, LevelSyllabus] = {}

    # 构建累积词汇
    cumulative_vocab: Dict[int, set] = {}
    for level in range(1, 10):
        key = "7-9" if level >= 7 else str(level)
        prev = cumulative_vocab.get(level - 1, set()) if level > 1 else set()
        cumulative_vocab[level] = prev | set(raw.get("vocabulary", {}).get(key, []))

    raw_recog = raw.get("char_recognition_cumulative", {})
    raw_write = raw.get("char_writing_cumulative", {})

    for level in range(1, 10):
        key = "7-9" if level >= 7 else str(level)
        stage, band = _STAGE_MAP[level]
        write_key = "1-2" if level <= 2 else key

        result[level] = LevelSyllabus(
            level=level, stage=stage, band=band,
            tasks=raw.get("tasks", {}).get(key, ""),
            grammar=raw.get("grammar", {}).get(key, ""),
            topics=raw.get("topics", {}).get(key, ""),
            vocabulary=frozenset(cumulative_vocab[level]),
            char_recognition=frozenset(raw_recog.get(key, [])),
            char_writing=frozenset(raw_write.get(write_key, [])),
        )
    return result


SYLLABUS: Dict[int, LevelSyllabus] = _build_syllabus()


def get_syllabus(level: int) -> LevelSyllabus:
    """获取指定等级的考纲数据。"""
    if level not in SYLLABUS:
        raise ValueError(f"HSK 3.0 level must be 1-9, got {level}")
    return SYLLABUS[level]


def _syllabus_field(fn: Callable[[LevelSyllabus], T]) -> Callable[[int], T]:
    """装饰器：将 get_xxx(syllabus) → get_xxx(level) 的样板 getter 简化为一行。"""
    @lru_cache(maxsize=9)
    def getter(level: int) -> T:
        return fn(get_syllabus(level))
    getter.__name__ = fn.__name__
    getter.__qualname__ = fn.__qualname__
    getter.__doc__ = fn.__doc__
    return getter


@_syllabus_field
def get_tasks(s: LevelSyllabus) -> str:
    """获取指定等级的任务大纲。"""
    return s.tasks


@_syllabus_field
def get_grammar(s: LevelSyllabus) -> str:
    """获取指定等级的语法大纲。"""
    return s.grammar


@_syllabus_field
def get_vocabulary(s: LevelSyllabus) -> FrozenSet[str]:
    """获取指定等级的累积词汇集（含 1..level 所有词汇）。"""
    return s.vocabulary


@_syllabus_field
def get_recognition_chars(s: LevelSyllabus) -> frozenset[str]:
    """获取指定等级的累积认读字集。"""
    return s.char_recognition


@_syllabus_field
def get_writing_chars(s: LevelSyllabus) -> frozenset[str]:
    """获取指定等级的累积书写字集。"""
    return s.char_writing
