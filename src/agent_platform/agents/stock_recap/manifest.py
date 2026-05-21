"""stock-recap AgentDefinition + 注册函数。

策略：
- 用 ``runner`` 入口包装现有 ``generate_once`` / ``iter_generate_ndjson``；
  现有 phase 函数与 RecapAgentRunState 暂保持不变（后续 commit 类化迁入此包）；
- 业务模型 (``GenerateRequest`` / ``GenerateResponse``) 仍住在 ``domain.models``，
  通过本 manifest 引用，保持兼容；
- ``mcp_tool_names`` / ``skills`` 显式声明依赖，便于 runtime 启动校验。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterator

from agent_platform.application.recap import generate_once, iter_generate_ndjson
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
from agent_platform.domain.models import GenerateRequest, GenerateResponse

logger = logging.getLogger("agent_platform.agents.stock_recap.manifest")

AGENT_ID = "stock-recap"


def _runner(
    *,
    envelope: AgentRequestEnvelope,
    principal: PrincipalContext,
    session: SessionContext,
    run_ctx: RunContext,
    settings: Any,
    runtime: Any,
):
    """统一入口：根据 envelope.stream 走 generate_once / iter_generate_ndjson。"""
    req = GenerateRequest.model_validate(envelope.payload)
    if envelope.stream:
        return _stream(req, settings, run_ctx)
    resp: GenerateResponse = generate_once(req, settings, ctx=run_ctx)
    return AgentResponseEnvelope(
        agent_id=AGENT_ID,
        request_id=run_ctx.request_id,
        payload=resp.model_dump(),
        rendered={
            "markdown": resp.rendered_markdown or "",
            "wechat_text": resp.rendered_wechat_text or "",
        },
        errors=[resp.error] if resp.error else [],
    )


def _stream(
    req: GenerateRequest, settings: Any, run_ctx: RunContext
) -> Iterator[Dict[str, Any]]:
    """NDJSON 流（每行已是 JSON 字符串）— 适配 runtime.stream 的 dict 返回约定。"""
    import json

    for line in iter_generate_ndjson(req, settings, ctx=run_ctx):
        try:
            yield json.loads(line)
        except Exception:
            # 与现有 NDJSON 协议保持兼容：若上游已是 dict-like，原样透出
            yield {"raw": line}


_DESCRIPTION = (
    "A 股市场的『日终复盘 / 次日策略』报告型智能体：基于当日行情、情绪、板块等数据，"
    "生成结构化 Markdown / 企微推送文本；支持 mock / live / akshare 数据源。"
)


def _build_definition() -> AgentDefinition:
    return AgentDefinition(
        id=AGENT_ID,
        display_name="A 股复盘智能体",
        description=_DESCRIPTION,
        request_model=GenerateRequest,
        response_model=GenerateResponse,
        capabilities=[
            AgentCapability.REPORT,
            AgentCapability.STREAMING,
            AgentCapability.SCHEDULED,
            AgentCapability.TOOL_USING,
        ],
        runner=_runner,
        mcp_tool_names=["web_search", "query_market_data", "query_history"],
        skills=["a_share_daily_recap", "a_share_strategy_nextday"],
        renderers=["markdown", "wechat_text"],
        cli_help="A 股日终复盘 / 次日策略",
        http_path_prefix="/v1/recap",
    )


def register(registry: AgentRegistry) -> None:
    """供 ``runtime.factory`` 与 entry_points 调用。"""
    registry.register(_build_definition())
    logger.debug("registered agent id=%s", AGENT_ID)


__all__ = ["AGENT_ID", "register"]
