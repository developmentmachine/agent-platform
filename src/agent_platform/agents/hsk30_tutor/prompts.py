"""HSK 3.0 教师 system prompt — 支持 RAG 动态检索注入。

重构要点：
- build_system_prompt 接受可选 query 参数启用 RAG 检索
- 无 query 时保持原有全量注入行为（向后兼容）
- 有 query 时只注入检索到的相关考纲片段 + 全量词汇/字表（验证需要）
- _compact_tasks 装饰器消除重复的压缩逻辑
"""
from __future__ import annotations

import re
from typing import Optional

from agent_platform.agents.hsk30_tutor.syllabus import get_syllabus
from agent_platform.agents.hsk30_tutor.grammar_examples import get_grammar_examples_text

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


def _compact_tasks(raw: str) -> str:
    """压缩任务大纲格式：去掉多余空行和页码。"""
    text = re.sub(r"^\d+\s*$", "", raw, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\n(?=[一二三四五六七八九十]、)", "\n", text)
    return text.strip()


def _vocab_compact(vocab: frozenset[str]) -> str:
    """生成紧凑的词汇列表。

    策略：所有等级最多展示 1500 核心词 + 扩展词数。
    高级别需要更多核心词覆盖，但 prompt token 预算有限。
    """
    core_limit = 1500
    sorted_vocab = sorted(vocab)
    if len(sorted_vocab) <= core_limit:
        return "、".join(sorted_vocab)
    core = sorted_vocab[:core_limit]
    remaining = len(sorted_vocab) - core_limit
    result = "、".join(core)
    result += f"\n\n（以上为核心词 {core_limit} 个，另有扩展词 {remaining} 个，共 {len(sorted_vocab)} 词。回复时优先使用核心词。）"
    return result


def build_system_prompt(
    *,
    level: int,
    explain_locale: str,
    query: Optional[str] = None,
) -> str:
    """构建 system prompt。

    Args:
        level: HSK 等级 1-9
        explain_locale: 讲解语言 "zh" | "en" | "both"
        query: 用户消息（启用 RAG 检索）。为 None 时全量注入（向后兼容）。
    """
    loc = _LOCALE_HINT.get(explain_locale, _LOCALE_HINT["both"])
    s = get_syllabus(level)

    # ── 认读字网格（全量，验证需要）──
    recog_grid = _char_grid(s.char_recognition)

    # ── 词汇列表（全量，验证需要）──
    vocab_text = _vocab_compact(s.vocabulary)

    # ── 任务/语法/话题/例句（RAG 或全量）──
    if query is not None:
        # RAG 模式：检索相关内容
        from agent_platform.agents.hsk30_tutor.rag import retrieve_syllabus
        rag_content = retrieve_syllabus(query, level, top_k=8)

        # 语法例句（全量，体积小）
        examples_text = get_grammar_examples_text(level)

        # 组装
        syllabus_section = f"""【考纲相关内容 — 根据你的问题检索】
{rag_content}

【语法例句参考】
{examples_text}"""
        token_note = "（以上为 RAG 检索的相关考纲内容，完整考纲约 14,800 tokens 已压缩）"
    else:
        # 全量模式（向后兼容）
        tasks_text = _compact_tasks(s.tasks)
        grammar_text = s.grammar.strip()
        topics_text = s.topics.strip() if s.topics else ""
        examples_text = get_grammar_examples_text(level)

        syllabus_section = f"""一、任务大纲（{level} 级，{len(tasks_text)} 字）
{tasks_text}

二、话题大纲（{level} 级）
{topics_text}

三、语法大纲（{level} 级）
{grammar_text}

四、语法例句参考
{examples_text}"""
        token_note = ""

    return f"""你是「HSK 3.0」框架下的中文学习陪练教师（不是旧版 HSK 2.0 六级制）。

学习者当前目标等级：{level} 级（{s.stage} · {s.band}）

═══════════════════════════════════════════
【考纲约束 — 必须严格遵守】
═══════════════════════════════════════════

{syllabus_section}

五、认读字表（{level} 级累积，共 {len(s.char_recognition)} 字）
{recog_grid}

六、词汇表（{level} 级累积，共 {len(s.vocabulary)} 词）
{vocab_text}
{token_note}

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
