"""HTTP：``POST /v1/hsk30-tutor/chat`` + ``POST /v1/hsk30-tutor/chat/stream``。

重构要点：
- 路由函数更紧凑，减少垂直间距
- 使用 FastAPI 的 Depends 链保持清晰
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent_platform.core.http import require_api_key, require_rate_limit
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.use_case import chat_turn
from agent_platform.config.settings import Settings, get_settings
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
def _create_runtime(settings=None):
    from agent_platform.runtime.factory import create_runtime as _factory_create
    return _factory_create(settings)

# Alias for test monkeypatching
create_runtime = _create_runtime

router = APIRouter(prefix="/v1/hsk30-tutor", tags=["hsk30-tutor"])


@router.post("/chat", response_model=TutorChatResponse)
def tutor_chat(body: TutorChatRequest, settings: Settings = Depends(get_settings),
               _p: PrincipalContext = Depends(require_api_key),
               _r: None = Depends(require_rate_limit)) -> TutorChatResponse:
    envelope = create_runtime(settings).run(agent_id="hsk30-tutor", payload=body.model_dump(), principal=_p)
    return TutorChatResponse.model_validate(envelope.payload)


@router.post("/chat/stream")
def tutor_chat_stream(body: TutorChatRequest, settings: Settings = Depends(get_settings),
                      _p: PrincipalContext = Depends(require_api_key),
                      _r: None = Depends(require_rate_limit)) -> StreamingResponse:
    """流式对话端点：返回 NDJSON 流。"""
    runtime = create_runtime(settings)
    return StreamingResponse(
        (json.dumps(e, ensure_ascii=False) + "\n" for e in runtime.stream(
            agent_id="hsk30-tutor", payload=body.model_dump(), principal=_p)),
        media_type="application/x-ndjson",
    )


@router.post("/chat/direct", response_model=TutorChatResponse, include_in_schema=False)
def tutor_chat_direct(body: TutorChatRequest, settings: Settings = Depends(get_settings),
                      _r: None = Depends(require_rate_limit)) -> TutorChatResponse:
    """不经 AgentRuntime 的直连路径（集成测试用）。"""
    return chat_turn(body, settings, ctx=RunContext.new())
