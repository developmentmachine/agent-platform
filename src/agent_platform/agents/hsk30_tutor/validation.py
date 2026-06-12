"""HSK 3.0 输出验证 — 检查 agent 回复是否符合等级字词约束。

验证两层：
1. 汉字级：每个汉字是否在认读字表内
2. 词汇级：分词后每个词是否在词汇表内（最大正向匹配）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List, Set, Tuple

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus


@dataclass
class ValidationResult:
    """验证结果。"""

    level: int
    valid: bool
    out_of_recognition: List[str]       # 超纲认读字
    out_of_vocabulary: List[str]        # 超纲词汇
    total_chinese_chars: int            # 总汉字数
    total_words: int                    # 总词数
    char_coverage_pct: float            # 汉字覆盖率
    word_coverage_pct: float            # 词汇覆盖率

    @property
    def summary(self) -> str:
        parts = []
        if self.out_of_recognition:
            chars_str = "、".join(self.out_of_recognition[:15])
            more = f"等 {len(self.out_of_recognition)} 字" if len(self.out_of_recognition) > 15 else ""
            parts.append(f"超纲字 {len(self.out_of_recognition)} 个：{chars_str}{more}")
        if self.out_of_vocabulary:
            words_str = "、".join(self.out_of_vocabulary[:10])
            more = f"等 {len(self.out_of_vocabulary)} 词" if len(self.out_of_vocabulary) > 10 else ""
            parts.append(f"超纲词 {len(self.out_of_vocabulary)} 个：{words_str}{more}")

        if self.valid:
            return (
                f"✅ 通过（{self.total_chinese_chars} 汉字 / "
                f"{self.total_words} 词，100% 在考纲范围内）"
            )
        return "⚠️ " + "；".join(parts)


def _extract_chinese_segments(text: str) -> List[str]:
    """提取连续中文文本段。"""
    return re.findall(r"[\u4e00-\u9fff]+", text)


def _forward_max_match(text: str, vocab: FrozenSet[str], max_len: int = 8) -> List[str]:
    """正向最大匹配分词。"""
    words = []
    i = 0
    while i < len(text):
        matched = False
        for length in range(min(max_len, len(text) - i), 0, -1):
            candidate = text[i : i + length]
            if candidate in vocab:
                words.append(candidate)
                i += length
                matched = True
                break
        if not matched:
            # 单字作为 fallback
            words.append(text[i])
            i += 1
    return words


def validate_reply(text: str, level: int) -> ValidationResult:
    """验证回复文本是否符合指定等级的字词约束。"""
    s = get_syllabus(level)
    recog = s.char_recognition
    vocab_set: FrozenSet[str] = frozenset(s.vocabulary)

    # ── 汉字级验证 ──
    chinese_chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    out_of_recog = sorted({ch for ch in chinese_chars if ch not in recog})
    total_chars = len(chinese_chars)
    char_pct = ((total_chars - len(out_of_recog)) / total_chars * 100) if total_chars > 0 else 100.0

    # ── 词汇级验证 ──
    segments = _extract_chinese_segments(text)
    all_words: List[str] = []
    out_of_vocab_set: Set[str] = set()

    for seg in segments:
        words = _forward_max_match(seg, vocab_set)
        all_words.extend(words)
        for w in words:
            if len(w) > 1 and w not in vocab_set:
                # 多字词不在词汇表中
                out_of_vocab_set.add(w)
            elif len(w) == 1 and w not in vocab_set:
                # 单字词：如果不在认读字表才算超纲
                if w not in recog:
                    out_of_vocab_set.add(w)

    total_words = len(all_words)
    out_of_vocab = sorted(out_of_vocab_set)
    word_pct = ((total_words - len(out_of_vocab)) / total_words * 100) if total_words > 0 else 100.0

    valid = len(out_of_recog) == 0 and len(out_of_vocab) == 0

    return ValidationResult(
        level=level,
        valid=valid,
        out_of_recognition=out_of_recog,
        out_of_vocabulary=out_of_vocab,
        total_chinese_chars=total_chars,
        total_words=total_words,
        char_coverage_pct=char_pct,
        word_coverage_pct=word_pct,
    )
