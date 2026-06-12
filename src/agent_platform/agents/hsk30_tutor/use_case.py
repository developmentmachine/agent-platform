"""HSK 3.0 Tutor 用例：组装 prompt → LLM/stub → 验证(含重试) → 响应。

重构要点：
- @with_agent_scope 装饰器消除 AgentScope 模板代码
- _validate_and_retry 统一验证+重试逻辑
"""
from __future__ import annotations

import functools
import logging
from typing import Dict, Iterator, List, Tuple

from agent_platform.agents.hsk30_tutor import AGENT_ID
from agent_platform.agents.hsk30_tutor.llm_client import chat_completion, chat_completion_stream
from agent_platform.agents.hsk30_tutor.models import ChatTurn, TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.prompts import build_system_prompt
from agent_platform.agents.hsk30_tutor.validation import ValidationResult, validate_reply
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.agent_scope import AgentScope, current_agent_scope

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.use_case")

_MAX_CORRECTION_ATTEMPTS = 2


# ── 装饰器：消除 AgentScope 设置/清理的模板代码 ──────────────────

def _with_agent_scope(fn):
    """为函数自动设置 AgentScope 上下文，结束后自动清理。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        scope = AgentScope(agent_id=AGENT_ID, mcp_tool_names=frozenset(),
                           skill_ids=frozenset(), skill_mode_map={})
        token = current_agent_scope.set(scope)
        try:
            return fn(*args, **kwargs)
        finally:
            current_agent_scope.reset(token)
    return wrapper


# ── 内部工具 ─────────────────────────────────────────────────

def _build_messages(req: TutorChatRequest) -> List[Dict[str, str]]:
    """组装 system + history + user 消息列表。"""
    return [
        {"role": "system", "content": build_system_prompt(level=req.level, explain_locale=req.explain_locale)},
        *({"role": t.role, "content": t.content} for t in req.history),
        {"role": "user", "content": req.message},
    ]


def _build_correction_message(validation: ValidationResult) -> str:
    """根据验证结果生成修正指令。"""
    parts = ["你刚才的回复包含了超出当前等级考纲的内容，请严格修正："]
    if validation.out_of_recognition:
        parts.append(f"超纲认读字（必须替换）：{'、'.join(validation.out_of_recognition[:20])}")
    if validation.out_of_vocabulary:
        parts.append(f"超纲词汇（必须替换）：{'、'.join(validation.out_of_vocabulary[:15])}")
    parts.append("请重新回答，严格只使用上方认读字表和词汇表中的字词。禁止使用以上超纲内容，用等级内的近义字词改述。")
    return "\n".join(parts)


def _validate_and_retry(
    messages: List[Dict[str, str]],
    reply: str,
    level: int,
    settings: Settings,
    backend: str = "llm",
) -> Tuple[str, ValidationResult]:
    """验证回复，若失败则带修正指令重试。返回 (best_reply, validation)。"""
    validation = validate_reply(reply, level)
    if backend == "stub" or validation.valid:
        return reply, validation

    for attempt in range(_MAX_CORRECTION_ATTEMPTS):
        logger.info("HSK level %d validation failed (attempt %d/%d): chars=%d vocab=%d",
                     level, attempt + 1, _MAX_CORRECTION_ATTEMPTS,
                     len(validation.out_of_recognition), len(validation.out_of_vocabulary))

        new_reply, new_backend = chat_completion(settings, [
            *messages,
            {"role": "assistant", "content": reply},
            {"role": "user", "content": _build_correction_message(validation)},
        ])
        if new_backend == "stub":
            break

        new_validation = validate_reply(new_reply, level)
        if new_reply and new_validation.char_coverage_pct >= validation.char_coverage_pct:
            reply, validation = new_reply, new_validation
        if validation.valid:
            break

    return reply, validation


# ── 对外接口 ─────────────────────────────────────────────────

@_with_agent_scope
def chat_turn(req: TutorChatRequest, settings: Settings, *, ctx: RunContext | None = None) -> TutorChatResponse:
    run_ctx = (ctx or RunContext.new()).with_overrides(agent_id=AGENT_ID)
    messages = _build_messages(req)
    reply, backend = chat_completion(settings, messages)

    note = None
    if backend == "stub":
        note = "未连接 LLM；设置 OPENAI_API_KEY 后启用完整陪练。"
    else:
        reply, validation = _validate_and_retry(messages, reply, req.level, settings, backend)
        if not validation.valid:
            logger.warning("HSK level %d validation: chars=%d vocab=%d (after retries)",
                           req.level, len(validation.out_of_recognition), len(validation.out_of_vocabulary))
            note = validation.summary

    return TutorChatResponse(reply=reply, level=req.level, request_id=run_ctx.request_id,
                             backend=backend, note=note)  # type: ignore[arg-type]


@_with_agent_scope
def chat_turn_stream(req: TutorChatRequest, settings: Settings, *, ctx: RunContext | None = None,
                     ) -> Iterator[Tuple[str, str]]:
    """流式版本：yield (chunk_text, backend_tag)，流结束后验证全文。"""
    messages = _build_messages(req)

    full_reply, backend = "", "stub"
    for chunk_text, be in chat_completion_stream(settings, messages):
        full_reply += chunk_text
        backend = be
        yield chunk_text, be

    if backend != "stub" and full_reply:
        validation = validate_reply(full_reply, req.level)
        if not validation.valid:
            logger.info("Stream validation failed for level %d: chars=%d vocab=%d",
                        req.level, len(validation.out_of_recognition), len(validation.out_of_vocabulary))
            yield f"\n\n[系统提示] {validation.summary}", "validation_note"
