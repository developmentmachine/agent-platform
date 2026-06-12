"""HSK 3.0 输出验证 — 检查 agent 回复是否符合等级字词约束。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus


@dataclass
class ValidationResult:
    """验证结果。"""

    level: int
    valid: bool
    out_of_recognition: List[str]      # 超纲认读字
    total_chinese_chars: int           # 总汉字数
    coverage_pct: float                # 覆盖率

    @property
    def summary(self) -> str:
        if self.valid:
            return f"✅ 通过（{self.total_chinese_chars} 汉字，100% 在认读字范围内）"
        chars_str = "、".join(self.out_of_recognition[:20])
        more = f"等 {len(self.out_of_recognition)} 字" if len(self.out_of_recognition) > 20 else ""
        return (
            f"⚠️ 发现 {len(self.out_of_recognition)} 个超纲字：{chars_str}{more}"
            f"（覆盖率 {self.coverage_pct:.1f}%）"
        )


def validate_reply(text: str, level: int) -> ValidationResult:
    """验证回复文本是否符合指定等级的认读字约束。"""
    s = get_syllabus(level)
    recog = s.char_recognition

    chinese_chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    out_of_recog = sorted({ch for ch in chinese_chars if ch not in recog})
    total = len(chinese_chars)
    covered = total - len([ch for ch in chinese_chars if ch not in recog])
    pct = (covered / total * 100) if total > 0 else 100.0

    return ValidationResult(
        level=level,
        valid=len(out_of_recog) == 0,
        out_of_recognition=out_of_recog,
        total_chinese_chars=total,
        coverage_pct=pct,
    )
