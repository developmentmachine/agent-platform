"""HSK 3.0 Tutor 单元测试：验证模块、Prompt 模块、syllabus 数据完整性。"""
from __future__ import annotations

import pytest

from agent_platform.agents.hsk30_tutor.syllabus import (
    SYLLABUS,
    get_recognition_chars,
    get_syllabus,
    get_vocabulary,
    get_writing_chars,
)
from agent_platform.agents.hsk30_tutor.validation import (
    ValidationResult,
    _forward_max_match,
    validate_reply,
)
from agent_platform.agents.hsk30_tutor.prompts import build_system_prompt, stage_label


# ── syllabus 数据完整性 ──────────────────────────────────────


class TestSyllabusIntegrity:
    """验证考纲数据的完整性和累积性。"""

    def test_all_nine_levels_exist(self):
        assert set(SYLLABUS.keys()) == set(range(1, 10))

    def test_vocabulary_cumulative(self):
        """Level N 词汇 ⊇ Level N-1 词汇。"""
        for level in range(2, 10):
            prev = set(SYLLABUS[level - 1].vocabulary)
            curr = set(SYLLABUS[level].vocabulary)
            missing = prev - curr
            assert not missing, f"Level {level} vocab missing {len(missing)} from Level {level-1}"

    def test_recognition_cumulative(self):
        """Level N 认读字 ⊇ Level N-1 认读字。"""
        for level in range(2, 10):
            prev = SYLLABUS[level - 1].char_recognition
            curr = SYLLABUS[level].char_recognition
            missing = prev - curr
            assert not missing, f"Level {level} recog missing {len(missing)} chars from Level {level-1}"

    def test_writing_cumulative(self):
        """Level N 书写字 ⊇ Level N-1 书写字。"""
        for level in range(2, 10):
            prev = SYLLABUS[level - 1].char_writing
            curr = SYLLABUS[level].char_writing
            missing = prev - curr
            assert not missing, f"Level {level} write missing {len(missing)} chars from Level {level-1}"

    def test_data_not_empty(self):
        """每个等级都有非空的任务大纲、语法大纲、词汇、认读字、书写字。"""
        for level in range(1, 10):
            s = SYLLABUS[level]
            assert s.tasks.strip(), f"Level {level}: tasks empty"
            assert s.grammar.strip(), f"Level {level}: grammar empty"
            assert s.vocabulary, f"Level {level}: vocabulary empty"
            assert s.char_recognition, f"Level {level}: char_recognition empty"
            assert s.char_writing, f"Level {level}: char_writing empty"

    def test_level_1_recog_size(self):
        """Level 1 认读字约 245 个。"""
        assert 200 <= len(SYLLABUS[1].char_recognition) <= 300

    def test_level_7_recog_size(self):
        """Level 7-9 认读字约 3086 个。"""
        assert 3000 <= len(SYLLABUS[7].char_recognition) <= 3200

    def test_total_vocab_size(self):
        """Level 7-9 总词汇约 10370 个。"""
        assert 10000 <= len(SYLLABUS[7].vocabulary) <= 11000

    def test_stage_mapping(self):
        assert SYLLABUS[1].stage == "初等"
        assert SYLLABUS[4].stage == "中等"
        assert SYLLABUS[7].stage == "高等"

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="HSK 3.0 level must be 1-9"):
            get_syllabus(0)
        with pytest.raises(ValueError, match="HSK 3.0 level must be 1-9"):
            get_syllabus(10)


# ── validate_reply ───────────────────────────────────────────


class TestValidateReply:
    """验证 validate_reply 的各种场景。"""

    def test_pure_level1_text_passes(self):
        """完全使用 Level 1 认读字的文本应通过。"""
        # Level 1 的认读字包含这些基础字
        recog = get_recognition_chars(1)
        # 用 Level 1 认读字构造简单文本
        sample_chars = sorted(recog)[:10]
        text = "".join(sample_chars)
        result = validate_reply(text, 1)
        assert result.valid is True
        assert result.char_coverage_pct == 100.0

    def test_out_of_syllabus_chars_detected(self):
        """超出 Level 1 的汉字应被检测到。"""
        # "饕餮" 不在 Level 1 认读字中
        result = validate_reply("饕餮", 1)
        assert result.valid is False
        assert "饕" in result.out_of_recognition
        assert "餮" in result.out_of_recognition

    def test_empty_text_passes(self):
        """空文本应通过。"""
        result = validate_reply("", 1)
        assert result.valid is True
        assert result.total_chinese_chars == 0

    def test_non_chinese_text_passes(self):
        """纯英文文本应通过（无汉字可检查）。"""
        result = validate_reply("Hello world!", 1)
        assert result.valid is True
        assert result.total_chinese_chars == 0

    def test_punctuation_ignored(self):
        """标点符号不影响验证。"""
        result = validate_reply("你好！我很好。", 1)
        # "你好我很好" 都在 Level 1 认读字中
        assert result.valid is True

    def test_higher_level_more_permissive(self):
        """高等级应比低等级更宽松。"""
        text = "经济发展是国家的重要目标"
        r1 = validate_reply(text, 1)
        r7 = validate_reply(text, 7)
        # Level 7 应该比 Level 1 容纳更多字
        assert len(r7.out_of_recognition) <= len(r1.out_of_recognition)

    def test_validation_result_summary_valid(self):
        result = ValidationResult(
            level=1, valid=True,
            out_of_recognition=[], out_of_vocabulary=[],
            total_chinese_chars=10, total_words=5,
            char_coverage_pct=100.0, word_coverage_pct=100.0,
        )
        assert "通过" in result.summary

    def test_validation_result_summary_invalid(self):
        result = ValidationResult(
            level=1, valid=False,
            out_of_recognition=["饕", "餮"], out_of_vocabulary=["饕餮"],
            total_chinese_chars=10, total_words=5,
            char_coverage_pct=80.0, word_coverage_pct=80.0,
        )
        assert "超纲字" in result.summary
        assert "超纲词" in result.summary


# ── _forward_max_match ───────────────────────────────────────


class TestForwardMaxMatch:
    """正向最大匹配分词测试。"""

    def test_single_word_match(self):
        from agent_platform.agents.hsk30_tutor.syllabus import SYLLABUS
        vocab = frozenset(["你好", "我", "是"])
        words = _forward_max_match("你好", vocab)
        assert words == ["你好"]

    def test_multi_word_match(self):
        vocab = frozenset(["你", "好", "你好"])
        words = _forward_max_match("你好", vocab)
        # 应该匹配最长的 "你好"
        assert words == ["你好"]

    def test_unknown_chars_fallback(self):
        vocab = frozenset(["你", "好"])
        words = _forward_max_match("你饕", vocab)
        assert "你" in words
        assert "饕" in words  # 单字 fallback

    def test_empty_text(self):
        words = _forward_max_match("", frozenset(["你好"]))
        assert words == []


# ── build_system_prompt ──────────────────────────────────────


class TestBuildSystemPrompt:
    """Prompt 生成测试。"""

    def test_prompt_contains_level_info(self):
        prompt = build_system_prompt(level=1, explain_locale="both")
        assert "1" in prompt
        assert "初等" in prompt

    def test_prompt_contains_teaching_rules(self):
        prompt = build_system_prompt(level=3, explain_locale="zh")
        assert "字词约束" in prompt
        assert "认读字表" in prompt
        assert "词汇表" in prompt

    def test_prompt_contains_locale_hint(self):
        prompt_zh = build_system_prompt(level=1, explain_locale="zh")
        assert "中文" in prompt_zh

        prompt_en = build_system_prompt(level=1, explain_locale="en")
        assert "English" in prompt_en

    def test_prompt_not_empty_for_all_levels(self):
        for level in range(1, 10):
            prompt = build_system_prompt(level=level, explain_locale="both")
            assert len(prompt) > 500, f"Level {level} prompt too short: {len(prompt)}"

    def test_prompt_includes_grammar_examples(self):
        prompt = build_system_prompt(level=1, explain_locale="both")
        assert "语法例句" in prompt

    def test_stage_label_format(self):
        label = stage_label(1)
        assert "初等" in label
        assert "Level 1" in label
        assert "基础" in label or "日常" in label

    def test_compact_tasks_does_not_strip_numbers(self):
        """_compact_tasks 不应删除任务大纲中的数字。"""
        from agent_platform.agents.hsk30_tutor.prompts import _compact_tasks
        raw = "一、问候与介绍\n\nHSK 3 级考试\n\n123\n\n二、个人信息"
        result = _compact_tasks(raw)
        assert "3" in result  # "HSK 3 级" 的数字应保留
        assert "123" not in result  # 纯数字行应被删除
        assert "问候" in result

    def test_vocab_compact_low_level_full(self):
        """低级别词汇应全量展示。"""
        from agent_platform.agents.hsk30_tutor.prompts import _vocab_compact
        vocab = ("你好", "谢谢", "再见")
        result = _vocab_compact(vocab, 1)
        assert "你好" in result
        assert "谢谢" in result
        assert "再见" in result
