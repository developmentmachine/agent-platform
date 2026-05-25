"""stock-recap AgentDefinition + 注册函数。

策略：
- 用 ``runner`` 入口包装现有 ``generate_once`` / ``iter_generate_ndjson``；
- 业务模型 (``GenerateRequest`` / ``GenerateResponse``) 仍住在 ``domain.models``，
  通过本 manifest 引用，保持兼容；
- ``mcp_tool_names`` / ``skills`` 显式声明依赖，便于 runtime 启动校验；
- W6: ``cli_subparser_factory`` / ``cli_run_handler`` / ``http_router_factories``
  / ``scheduled_jobs`` 由本 manifest 声明，让 CLI / HTTP / Scheduler 装配器
  按 ``AgentRegistry`` 自动发现。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List

from agent_platform.agents.stock_recap.use_case import generate_once, iter_generate_ndjson
from agent_platform.core.registry.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
    ScheduledJob,
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


# ─── W6: CLI 子命令钩子 ─────────────────────────────────────────────────────


def _cli_subparser(sub: Any) -> None:
    from agent_platform.agents.stock_recap.cli import register_subparser

    register_subparser(sub)


def _cli_run(args: Any, settings: Any, parser: Any) -> int:
    from agent_platform.agents.stock_recap.cli import run as _run

    return _run(args, settings, parser)


# ─── W6: HTTP 路由钩子 ──────────────────────────────────────────────────────


def _http_routers() -> List[Any]:
    from agent_platform.agents.stock_recap.http_routes import feedback_router, recap_router

    return [recap_router, feedback_router]


# ─── W6: 调度任务钩子 ──────────────────────────────────────────────────────


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_trading_today() -> bool:
    from agent_platform.agents.stock_recap.data.calendar import is_trading_day

    today = datetime.now().strftime("%Y-%m-%d")
    return is_trading_day(today)


def _write_output_files(
    output_dir: str, date: str, mode: str, markdown: str, wechat: str | None
) -> None:
    import os

    os.makedirs(output_dir, exist_ok=True)
    base = f"recap_{date}_{mode}"
    with open(os.path.join(output_dir, base + ".md"), "w", encoding="utf-8") as f:
        f.write(markdown)
    if wechat:
        with open(os.path.join(output_dir, base + "_wechat.txt"), "w", encoding="utf-8") as f:
            f.write(wechat)


def _scheduled_handler(mode: str, settings: Any) -> None:
    """统一的 cron handler — daily_recap / strategy 都走这条。"""
    from agent_platform.agents.stock_recap.use_case import generate_once
    from agent_platform.infrastructure.persistence.db import init_db

    if not _is_trading_today():
        logger.info(_stable_json({"event": "scheduler_skip", "job": f"recap_{mode}", "reason": "non_trading_day"}))
        return
    logger.info(_stable_json({"event": "scheduler_start", "job": f"recap_{mode}"}))
    try:
        init_db(settings.db_path)
        req = GenerateRequest(mode=mode, provider="live", force_llm=True)
        resp = generate_once(req, settings)
        logger.info(
            _stable_json(
                {
                    "event": "scheduler_done",
                    "job": f"recap_{mode}",
                    "request_id": resp.request_id,
                }
            )
        )
        if resp.rendered_markdown and resp.snapshot is not None:
            _write_output_files(
                settings.output_dir,
                resp.snapshot.date,
                mode,
                resp.rendered_markdown,
                resp.rendered_wechat_text,
            )
    except Exception as e:
        logger.error(_stable_json({"event": "scheduler_error", "job": f"recap_{mode}", "error": str(e)}))


def _backtest_handler(settings: Any) -> None:
    from agent_platform.agents.stock_recap.use_case import _try_run_backtest

    if not _is_trading_today():
        return
    logger.info(_stable_json({"event": "scheduler_start", "job": "recap_backtest"}))
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        _try_run_backtest(settings.db_path, today)
        logger.info(_stable_json({"event": "scheduler_done", "job": "recap_backtest"}))
    except Exception as e:
        logger.error(_stable_json({"event": "scheduler_error", "job": "recap_backtest", "error": str(e)}))


def _build_scheduled_jobs(settings: Any) -> List[ScheduledJob]:
    return [
        ScheduledJob(
            id="stock_recap.daily",
            description="每日 15:30 自动生成日终复盘",
            cron_kwargs={
                "day_of_week": "mon-fri",
                "hour": settings.scheduler_daily_hour,
                "minute": settings.scheduler_daily_minute,
            },
            handler=lambda s: _scheduled_handler("daily", s),
        ),
        ScheduledJob(
            id="stock_recap.strategy",
            description="每日 15:35 自动生成次日策略",
            cron_kwargs={
                "day_of_week": "mon-fri",
                "hour": settings.scheduler_daily_hour,
                "minute": settings.scheduler_strategy_minute,
            },
            handler=lambda s: _scheduled_handler("strategy", s),
        ),
        ScheduledJob(
            id="stock_recap.backtest",
            description="每日 15:40 回测昨日策略",
            cron_kwargs={
                "day_of_week": "mon-fri",
                "hour": settings.scheduler_daily_hour,
                "minute": settings.scheduler_backtest_minute,
            },
            handler=_backtest_handler,
        ),
    ]


def _build_definition() -> AgentDefinition:
    from agent_platform.config.settings import get_settings

    # 调度任务的 cron 字段依赖运行时 settings；这里 lazy 解析仅在 build 时一次。
    settings = get_settings()
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
        cli_subparser_factory=_cli_subparser,
        cli_run_handler=_cli_run,
        http_router_factories=[_http_routers],
        scheduled_jobs=_build_scheduled_jobs(settings),
    )


def register(registry: AgentRegistry) -> None:
    """供 ``runtime.factory`` 与 entry_points 调用。"""
    registry.register(_build_definition())
    logger.debug("registered agent id=%s", AGENT_ID)


__all__ = ["AGENT_ID", "register"]
