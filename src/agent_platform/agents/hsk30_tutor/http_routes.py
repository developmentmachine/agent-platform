"""HTTP：``POST /v1/hsk30-tutor/chat``。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_platform.adapters.http.deps import require_api_key, require_rate_limit
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.use_case import chat_turn
from agent_platform.config.settings import Settings, get_settings
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.runtime.factory import create_runtime

router = APIRouter(prefix="/v1/hsk30-tutor", tags=["hsk30-tutor"])


@router.post("/chat", response_model=TutorChatResponse)
def tutor_chat(
    body: TutorChatRequest,
    settings: Settings = Depends(get_settings),
    _principal: PrincipalContext = Depends(require_api_key),
    _rate: None = Depends(require_rate_limit),
) -> TutorChatResponse:
    runtime = create_runtime(settings)
    envelope = runtime.run(
        agent_id="hsk30-tutor",
        payload=body.model_dump(),
        principal=_principal,
    )
    return TutorChatResponse.model_validate(envelope.payload)


@router.post("/chat/direct", response_model=TutorChatResponse, include_in_schema=False)
def tutor_chat_direct(
    body: TutorChatRequest,
    settings: Settings = Depends(get_settings),
    _rate: None = Depends(require_rate_limit),
) -> TutorChatResponse:
    """不经 AgentRuntime 的直连路径（集成测试用）。"""
    return chat_turn(body, settings, ctx=RunContext.new())
