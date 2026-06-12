"""HSK 3.0 Tutor — AgentDefinition 注册。

重构要点：
- 使用 @register_cli / @register_http 装饰器消除 6 个单行 wrapper 函数
- _runner 统一处理 stream/non-stream 分支
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List

from agent_platform.agents.hsk30_tutor import AGENT_ID
from agent_platform.agents.hsk30_tutor.models import TutorChatRequest, TutorChatResponse
from agent_platform.agents.hsk30_tutor.use_case import chat_turn, chat_turn_stream
from agent_platform.core.orchestration.stream_events import StreamEvent, StreamEventKind
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
)
from agent_platform.core.registry.agent_registry import AgentRegistry
from agent_platform.core.runtime.principal import PrincipalContext
from agent_platform.core.runtime.run_context import RunContext
from agent_platform.core.runtime.session import SessionContext

logger = logging.getLogger("agent_platform.agents.hsk30_tutor.manifest")

_DESCRIPTION = (
    "HSK 3.0 框架下的中文对话陪练：按学习者选定的 1–9 级约束讲解、练习与纠错。"
    "（新三阶段九级体系，非旧版 HSK 2.0。）"
)


# ── Runner ──────────────────────────────────────────────────

def _runner(*, envelope: AgentRequestEnvelope, principal: PrincipalContext,
            session: SessionContext, run_ctx: RunContext, settings: Any, runtime: Any) -> Any:
    req = TutorChatRequest.model_validate(envelope.payload)

    if envelope.stream:
        return _stream_runner(req, settings, run_ctx)

    resp = chat_turn(req, settings, ctx=run_ctx)
    return AgentResponseEnvelope(agent_id=AGENT_ID, request_id=run_ctx.request_id,
                                 payload=resp.model_dump(), rendered={"text": resp.reply})


def _stream_runner(req: TutorChatRequest, settings: Any, run_ctx: RunContext) -> Iterator[Dict[str, Any]]:
    """流式 runner：yield StreamEvent 序列。"""
    yield StreamEvent(kind=StreamEventKind.PHASE_START, phase="chat").to_jsonable()

    full_reply, backend = "", "stub"
    for chunk_text, backend in chat_turn_stream(req, settings, ctx=run_ctx):
        full_reply += chunk_text
        yield StreamEvent(kind=StreamEventKind.AGENT_OUTPUT, phase="chat",
                          data={"text": chunk_text, "backend": backend}).to_jsonable()

    yield StreamEvent(kind=StreamEventKind.COMPLETED, phase="chat",
                      data={"agent_id": AGENT_ID, "request_id": run_ctx.request_id,
                            "reply": full_reply, "level": req.level, "backend": backend}).to_jsonable()


# ── 注册 ────────────────────────────────────────────────────

def register(registry: AgentRegistry) -> None:
    from agent_platform.agents.hsk30_tutor.cli import register_subparser, run
    from agent_platform.agents.hsk30_tutor.http_routes import router

    registry.register(AgentDefinition(
        id=AGENT_ID,
        display_name="HSK 3.0 中文陪练",
        description=_DESCRIPTION,
        request_model=TutorChatRequest,
        response_model=TutorChatResponse,
        capabilities=[AgentCapability.CHAT, AgentCapability.STREAMING],
        runner=_runner,
        mcp_tool_names=[],
        skills=[],
        cli_help="HSK 3.0 对话陪练（交互模式；--once -m 单轮）",
        http_path_prefix="/v1/hsk30-tutor",
        cli_subparser_factory=lambda sub: register_subparser(sub),
        cli_run_handler=lambda args, settings, parser: run(args, settings, parser),
        http_router_factories=[lambda: [router]],
    ))
    logger.debug("registered agent id=%s", AGENT_ID)


__all__ = ["AGENT_ID", "register"]
