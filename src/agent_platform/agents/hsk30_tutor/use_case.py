"""HSK 3.0 Tutor 用例：组装 prompt → LLM/stub → 验证 → 响应。"""
from __future__ import annotations

import logging
from typing import List

from agent_platform.agents.hsk30_tutor import AGENT_ID
from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.prompts import build_system_prompt
from agent_platform.agents.hsk30_tutor.validation import validate_reply
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.agent_scope import AgentScope, current_agent_scope

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.use_case")


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
    messages: List[dict[str, str]] = [
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

    reply, backend = chat_completion(settings, messages)

    # ── 输出验证 ──
    note = None
    if backend == "stub":
        note = "未连接 LLM；设置 OPENAI_API_KEY 后启用完整陪练。"
    else:
        validation = validate_reply(reply, req.level)
        if not validation.valid:
            logger.warning(
                "HSK level %d validation: %d out-of-recognition chars: %s",
                req.level,
                len(validation.out_of_recognition),
                validation.out_of_recognition[:10],
            )
            note = validation.summary

    return TutorChatResponse(
        reply=reply,
        level=req.level,
        request_id=run_ctx.request_id,
        backend=backend,  # type: ignore[arg-type]
        note=note,
    )
