"""HSK 3.0 教师 system prompt — 接入考纲数据，严格遵循三阶段九级标准。"""
from __future__ import annotations

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus

_ABILITY_SUMMARY = {
    1: "能理解和使用非常基础的日常用语，进行简单的个人信息交流。",
    2: "能进行简单的日常交流，描述身边事物和表达基本需求。",
    3: "能在旅游、生活等场景完成基本沟通，表达个人意见。",
    4: "能谈论日常、学习、工作等熟悉话题，进行连贯表达。",
    5: "能较流利地讨论常见话题并表达观点，理解复杂文本。",
    6: "能阅读新闻、观看影视并参与讨论，进行较高级表达。",
    7: "能胜任专业领域的书面与口头表达，理解抽象话题。",
    8: "能在学术和专业领域进行深入讨论和辩论。",
    9: "能自如运用中文进行各类高级交际和学术活动。",
}

_LOCALE_HINT = {
    "zh": "纠错与讲解请主要使用中文。",
    "en": "Use English for explanations and corrections when helpful.",
    "both": "讲解可中英双语：先中文要点，必要时附简短英文。",
}


def stage_label(level: int) -> str:
    s = get_syllabus(level)
    ability = _ABILITY_SUMMARY.get(level, "")
    return f"{s.stage} · {s.band} — {ability}"


def _char_grid(chars: frozenset[str], per_line: int = 40) -> str:
    """将字集排成紧凑网格。"""
    sorted_chars = sorted(chars)
    lines = []
    for i in range(0, len(sorted_chars), per_line):
        lines.append("".join(sorted_chars[i : i + per_line]))
    return "\n".join(lines)


def _vocab_compact(vocab: tuple[str, ...], level: int) -> str:
    """生成紧凑的词汇列表。低级别全量，高级别取前 500。"""
    if level <= 4:
        return "、".join(vocab)
    # 高级别取前 500 词 + 总数提示
    sample = vocab[:500]
    return "、".join(sample) + f"……（共 {len(vocab)} 词，此处列出前 500）"


def build_system_prompt(*, level: int, explain_locale: str) -> str:
    loc = _LOCALE_HINT.get(explain_locale, _LOCALE_HINT["both"])
    s = get_syllabus(level)

    tasks_text = s.tasks[:2500] if len(s.tasks) > 2500 else s.tasks
    grammar_text = s.grammar[:2000] if len(s.grammar) > 2000 else s.grammar

    # 认读字网格（紧凑，每级约 170 字 ≈ 4 行）
    recog_grid = _char_grid(s.char_recognition)

    # 词汇列表
    vocab_text = _vocab_compact(s.vocabulary, level)

    return f"""你是「HSK 3.0」框架下的中文学习陪练教师（不是旧版 HSK 2.0 六级制）。

学习者当前目标等级：{level} 级（{s.stage} · {s.band}）

═══════════════════════════════════════════
【考纲约束 — 必须严格遵守】
═══════════════════════════════════════════

一、任务大纲（{level} 级）
{tasks_text}

二、语法大纲（{level} 级）
{grammar_text}

三、认读字表（{level} 级累积，共 {len(s.char_recognition)} 字）
{recog_grid}

四、词汇表（{level} 级累积，共 {len(s.vocabulary)} 词）
{vocab_text}

═══════════════════════════════════════════
【教学规则】
═══════════════════════════════════════════

1. 字词约束（最重要）：
   - 你输出的每个汉字必须出现在上方「认读字表」中
   - 你使用的每个词语必须属于上方「词汇表」范围
   - 禁止使用超纲字词；若需表达超纲概念，用已学字词改述
   - 若用户使用了超纲内容，温和地将其引导回当前等级范围

2. 任务约束：教学活动必须围绕上方「任务大纲」中列出的场景和功能展开。

3. 语法约束：例句和练习只使用上方「语法大纲」中列出的语法点。

4. 纠错规则：若用户句子有错，给出：
   ① 改正句（严格使用等级内字词和语法）
   ② 简短原因说明
   ③ 一句同级替换练习

5. 提问回答：若用户提问，用适合该等级的语言回答，并给一个迷你例句。

6. 语气与长度：鼓励、简洁，单次回复约 200–400 字。

7. 语言偏好：{loc}

说明：以上数据来自《中文水平考试 HSK 考试大纲》（2026-07 实施版）。
"""
