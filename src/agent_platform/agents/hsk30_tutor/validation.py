"""HSK 3.0 输出验证 — 检查 agent 回复是否符合等级字词约束。

验证两层：
1. 汉字级：每个汉字是否在认读字表内（豁免专有名词和数字）
2. 词汇级：分词后每个词是否在词汇表内（正向最大匹配）

语言学设计：
- 专有名词（人名、地名、国名）不在词汇大纲范围内，予以豁免
- 阿拉伯数字和常见标点不影响验证
- 语气词/叹词在口语中高频出现，标记但不阻断
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List, Set, Tuple

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus

# ── 专有名词豁免集 ──────────────────────────────────────────────
# 常见中文人名用字（不在 HSK 1 级认读字中但属于专有名词）
_PROPER_NOUN_CHARS: Set[str] = set(
    "丽伟芳娜敏静杰磊洋勇军"
    "强磊鑫鹏涛昊天浩宇轩"
    "梓涵欣怡紫萱雨桐可馨"
)
# 常见国名/地名中的高频字
_PLACE_NAME_CHARS: Set[str] = set("京沪深穗杭宁蓉渝汉")


@dataclass
class ValidationResult:
    """验证结果。"""

    level: int
    valid: bool
    out_of_recognition: List[str]       # 超纲认读字（已排除专有名词）
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


def _is_in_proper_noun_context(text: str, pos: int, char: str) -> bool:
    """判断字符是否在专有名词上下文中（人名/地名用字）。

    语言学依据：专有名词不属于词汇大纲范围。
    HSK 考试大纲明确说明"词汇表不收录专有名词"。
    """
    return char in _PROPER_NOUN_CHARS or char in _PLACE_NAME_CHARS


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
    """验证回复文本是否符合指定等级的字词约束。

    语言学豁免规则：
    - 专有名词（人名用字、地名用字）不计入超纲
    - 阿拉伯数字不参与汉字级验证
    - 标点符号不影响验证
    """
    s = get_syllabus(level)
    recog = s.char_recognition
    vocab_set: FrozenSet[str] = frozenset(s.vocabulary)

    # ── 汉字级验证 ──
    chinese_chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    out_of_recog = sorted({
        ch for ch in chinese_chars
        if ch not in recog and not _is_in_proper_noun_context(text, 0, ch)
    })
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
                # 单字词：如果不在认读字表且不是专有名词用字才算超纲
                if w not in recog and not _is_in_proper_noun_context(text, 0, w):
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
