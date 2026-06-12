"""HSK 3.0 考纲数据（2026-07 实施版）。

来源：《中文水平考试 HSK 考试大纲》中外语言交流合作中心 2025-11 发布。
包含：任务大纲、语法大纲、话题大纲、词汇表、认读字表、书写字表。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Dict, FrozenSet, List, Optional, Set

from agent_platform.agents import hsk30_tutor as _pkg


@dataclass(frozen=True)
class LevelSyllabus:
    """单个等级的考纲数据。"""

    level: int
    stage: str              # 初等 / 中等 / 高等
    band: str               # e.g. "Level 1", "Level 7–9"
    tasks: str              # 任务大纲原文
    grammar: str            # 语法大纲原文
    topics: str = ""        # 话题大纲原文
    vocabulary: tuple = ()  # 本级词汇 tuple[str, ...]
    char_recognition: frozenset = frozenset()  # 累积认读字
    char_writing: frozenset = frozenset()      # 累积书写字


_STAGE_MAP = {
    1: ("初等", "Level 1"),
    2: ("初等", "Level 2"),
    3: ("初等", "Level 3"),
    4: ("中等", "Level 4"),
    5: ("中等", "Level 5"),
    6: ("中等", "Level 6"),
    7: ("高等", "Level 7–9"),
    8: ("高等", "Level 7–9"),
    9: ("高等", "Level 7–9"),
}


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    ref = resources.files(_pkg).joinpath("syllabus_data.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _build_syllabus() -> Dict[int, LevelSyllabus]:
    raw = _load_raw()
    result: Dict[int, LevelSyllabus] = {}

    # Build cumulative vocabulary per level
    cumulative_vocab: Dict[int, List[str]] = {}
    for level in range(1, 10):
        key = "7-9" if level >= 7 else str(level)
        vocab = raw.get("vocabulary", {}).get(key, [])
        prev_level = level - 1 if level > 1 else None
        prev_vocab = set(cumulative_vocab.get(prev_level, [])) if prev_level else set()
        cumulative_vocab[level] = sorted(prev_vocab | set(vocab))

    # Character recognition - cumulative from raw data
    raw_recog = raw.get("char_recognition_cumulative", {})
    raw_write = raw.get("char_writing_cumulative", {})

    for level in range(1, 10):
        key = "7-9" if level >= 7 else str(level)
        stage, band = _STAGE_MAP[level]

        # Map level to cumulative key
        recog_key = key
        recog_chars = frozenset(raw_recog.get(recog_key, []))

        # Writing: levels 1-2 share a group
        if level <= 2:
            write_key = "1-2"
        else:
            write_key = key
        write_chars = frozenset(raw_write.get(write_key, []))

        result[level] = LevelSyllabus(
            level=level,
            stage=stage,
            band=band,
            tasks=raw.get("tasks", {}).get(key, ""),
            grammar=raw.get("grammar", {}).get(key, ""),
            topics=raw.get("topics", {}).get(key, ""),
            vocabulary=tuple(cumulative_vocab.get(level, [])),
            char_recognition=recog_chars,
            char_writing=write_chars,
        )
    return result


SYLLABUS: Dict[int, LevelSyllabus] = _build_syllabus()


def get_syllabus(level: int) -> LevelSyllabus:
    """获取指定等级的考纲数据。"""
    if level not in SYLLABUS:
        raise ValueError(f"HSK 3.0 level must be 1-9, got {level}")
    return SYLLABUS[level]


def get_tasks(level: int) -> str:
    """获取指定等级的任务大纲。"""
    return get_syllabus(level).tasks


def get_grammar(level: int) -> str:
    """获取指定等级的语法大纲。"""
    return get_syllabus(level).grammar


def get_vocabulary(level: int) -> tuple[str, ...]:
    """获取指定等级的累积词汇表（含 1..level 所有词汇）。"""
    return get_syllabus(level).vocabulary


def get_recognition_chars(level: int) -> frozenset[str]:
    """获取指定等级的累积认读字集。"""
    return get_syllabus(level).char_recognition


def get_writing_chars(level: int) -> frozenset[str]:
    """获取指定等级的累积书写字集。"""
    return get_syllabus(level).char_writing


def validate_text(text: str, level: int) -> dict:
    """验证文本是否符合指定等级的字词约束。

    Returns:
        {"valid": bool, "out_of_vocab": [...], "out_of_recog_chars": [...]}
    """
    s = get_syllabus(level)
    vocab_set = set(s.vocabulary)
    recog_set = s.char_recognition

    # Check individual characters
    out_of_recog = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' and ch not in recog_set:
            out_of_recog.append(ch)

    return {
        "valid": len(out_of_recog) == 0,
        "out_of_recog_chars": sorted(set(out_of_recog)),
        "total_chars_checked": sum(1 for c in text if '\u4e00' <= c <= '\u9fff'),
    }
