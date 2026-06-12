"""HSK 3.0 Tutor 用例：组装 prompt → LLM/stub → 验证(含重试) → 响应。"""
from __future__ import annotations

import logging
from typing import Dict, Iterator, List, Tuple

from agent_platform.agents.hsk30_tutor import AGENT_ID
from agent_platform.agents.hsk30_tutor.llm_client import chat_completion, chat_completion_stream
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.prompts import build_system_prompt
from agent_platform.agents.hsk30_tutor.validation import ValidationResult, validate_reply
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.agent_scope import AgentScope, current_agent_scope

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.use_case")

_MAX_CORRECTION_ATTEMPTS = 2


def _build_messages(req: TutorChatRequest) -> List[Dict[str, str]]:
    """组装 system + history + user 消息列表。"""
    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                level=req.level,
                explain_locale=req.explain_locale,
            ),
        },
    ]
    for turn in req.history:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.message})
    return messages


def _build_correction_message(validation: ValidationResult) -> str:
    """根据验证结果生成修正指令。"""
    parts = ["你刚才的回复包含了超出当前等级考纲的内容，请严格修正："]

    if validation.out_of_recognition:
        chars = "、".join(validation.out_of_recognition[:20])
        parts.append(f"超纲认读字（必须替换）：{chars}")

    if validation.out_of_vocabulary:
        words = "、".join(validation.out_of_vocabulary[:15])
        parts.append(f"超纲词汇（必须替换）：{words}")

    parts.append(
        "请重新回答，严格只使用上方认读字表和词汇表中的字词。"
        "禁止使用以上超纲内容，用等级内的近义字词改述。"
    )
    return "\n".join(parts)


def _validate_and_retry(
    messages: List[Dict[str, str]],
    reply: str,
    level: int,
    settings: Settings,
    backend: str = "llm",
) -> Tuple[str, ValidationResult]:
    """验证回复，若失败则带修正指令重试（最多 _MAX_CORRECTION_ATTEMPTS 次）。

    Returns:
        (best_reply, final_validation)
    """
    # stub 模式不验证不重试
    if backend == "stub":
        validation = validate_reply(reply, level)
        return reply, validation

    best_reply = reply
    validation = validate_reply(reply, level)

    if validation.valid:
        return reply, validation

    for attempt in range(_MAX_CORRECTION_ATTEMPTS):
        logger.info(
            "HSK level %d validation failed (attempt %d/%d): chars=%d vocab=%d",
            level, attempt + 1, _MAX_CORRECTION_ATTEMPTS,
            len(validation.out_of_recognition),
            len(validation.out_of_vocabulary),
        )
        # 追加 assistant 回复 + 修正指令
        correction_messages = list(messages)
        correction_messages.append({"role": "assistant", "content": reply})
        correction_messages.append({
            "role": "user",
            "content": _build_correction_message(validation),
        })

        new_reply, backend = chat_completion(settings, correction_messages)
        if backend == "stub":
            break  # stub 模式不重试

        new_validation = validate_reply(new_reply, level)
        # 选择覆盖率更高的回复
        if new_reply and (
            new_validation.char_coverage_pct >= validation.char_coverage_pct
        ):
            reply = new_reply
            validation = new_validation
            best_reply = new_reply

        if validation.valid:
            break

    return best_reply, validation


def chat_turn(
    req: TutorChatRequest,
    settings: Settings,
    *,
    ctx: RunContext | None = None,
) -> TutorChatResponse:
    scope = AgentScope(
        agent_id=AGENT_ID,
        mcp_tool_names=frozenset(),
        skill_ids=frozenset(),
        skill_mode_map={},
    )
    token = current_agent_scope.set(scope)
    try:
        return _chat_turn_scoped(req, settings, ctx=ctx)
    finally:
        current_agent_scope.reset(token)


def _chat_turn_scoped(
    req: TutorChatRequest,
    settings: Settings,
    *,
    ctx: RunContext | None = None,
) -> TutorChatResponse:
    run_ctx = (ctx or RunContext.new()).with_overrides(agent_id=AGENT_ID)
    messages = _build_messages(req)
    reply, backend = chat_completion(settings, messages)

    note = None
    if backend == "stub":
        note = "未连接 LLM；设置 OPENAI_API_KEY 后启用完整陪练。"
    else:
        # 验证 + 重试修正
        reply, validation = _validate_and_retry(messages, reply, req.level, settings, backend)
        if not validation.valid:
            logger.warning(
                "HSK level %d validation: chars=%d vocab=%d (after retries)",
                req.level,
                len(validation.out_of_recognition),
                len(validation.out_of_vocabulary),
            )
            note = validation.summary

    return TutorChatResponse(
        reply=reply,
        level=req.level,
        request_id=run_ctx.request_id,
        backend=backend,  # type: ignore[arg-type]
        note=note,
    )


def chat_turn_stream(
    req: TutorChatRequest,
    settings: Settings,
    *,
    ctx: RunContext | None = None,
) -> Iterator[Tuple[str, str]]:
    """流式版本：yield (chunk_text, backend_tag)。

    流结束后自动验证全文；若验证失败，追加一个修正提示 chunk。
    """
    scope = AgentScope(
        agent_id=AGENT_ID,
        mcp_tool_names=frozenset(),
        skill_ids=frozenset(),
        skill_mode_map={},
    )
    token = current_agent_scope.set(scope)
    try:
        run_ctx = (ctx or RunContext.new()).with_overrides(agent_id=AGENT_ID)
        messages = _build_messages(req)

        full_reply = ""
        backend = "stub"
        for chunk_text, be in chat_completion_stream(settings, messages):
            full_reply += chunk_text
            backend = be
            yield chunk_text, be

        # 流结束后验证（仅非 stub 模式）
        if backend != "stub" and full_reply:
            validation = validate_reply(full_reply, req.level)
            if not validation.valid:
                logger.info(
                    "Stream validation failed for level %d: chars=%d vocab=%d",
                    req.level,
                    len(validation.out_of_recognition),
                    len(validation.out_of_vocabulary),
                )
                # yield 一个修正提示作为额外 chunk
                correction_hint = f"\n\n[系统提示] {validation.summary}"
                yield correction_hint, "validation_note"
    finally:
        current_agent_scope.reset(token)
