"""HSK 3.0 Tutor 用例：组装 prompt → LLM/stub → 响应。"""
from __future__ import annotations

from typing import List

from agent_platform.agents.hsk30_tutor.llm_client import chat_completion
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.prompts import build_system_prompt
from agent_platform.config.settings import Settings
from agent_platform.core.runtime.run_context import RunContext


def chat_turn(
    req: TutorChatRequest,
    settings: Settings,
    *,
    ctx: RunContext | None = None,
) -> TutorChatResponse:
    run_ctx = ctx or RunContext.new()
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
    note = None
    if backend == "stub":
        note = "未连接 LLM；设置 OPENAI_API_KEY 后启用完整陪练。"

    return TutorChatResponse(
        reply=reply,
        level=req.level,
        request_id=run_ctx.request_id,
        backend=backend,  # type: ignore[arg-type]
        note=note,
    )
