"""生成复盘（同步 JSON）+ NDJSON 流式复盘 端点。

编排：FastAPI 依赖注入 → 输入护栏 → init_db → RunContext →
``generate_once``/``iter_generate_ndjson``；响应后将进化/回测挂到 BackgroundTasks。
"""
from __future__ import annotations

from typing import Iterator, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from agent_platform.agents.stock_recap.deps import StockRecapDeps, default_deps
from agent_platform.agents.stock_recap.use_case import generate_once, iter_generate_ndjson
from agent_platform.agents.stock_recap.effects.deferred import run_deferred_post_recap
from agent_platform.config.settings import Settings, get_settings
from agent_platform.domain.models import GenerateRequest, GenerateResponse
from agent_platform.domain.run_context import RunContext
from agent_platform.core.http import require_api_key, require_rate_limit
from agent_platform.core.ports.guardrail import GuardrailError, GuardrailPort

router = APIRouter(tags=["recap"])


def _get_deps() -> StockRecapDeps:
    return default_deps()


@router.post(
    "/v1/recap",
    response_model=GenerateResponse,
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)
def api_generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    deps: StockRecapDeps = Depends(_get_deps),
) -> JSONResponse:
    try:
        deps.guardrail.validate_generate_request(req)
    except GuardrailError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if deps.init_db is not None:
        deps.init_db(settings.db_path)
    ctx = RunContext.new(session_id=x_session_id)
    resp = generate_once(
        req,
        settings,
        ctx=ctx,
        defer_evolution_backtest=True,
        guardrail=deps.guardrail,
        repo_factory=deps.repo_factory,
    )
    background_tasks.add_task(
        run_deferred_post_recap,
        resp.request_id,
        req.mode,
        resp.snapshot.date,
        resp.recap is not None,
    )

    status = 200
    if req.force_llm and resp.recap is None:
        status = 503
    return JSONResponse(status_code=status, content=resp.model_dump())

@router.post(
    "/v1/recap/stream",
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)
def api_generate_stream(
    req: GenerateRequest,
    settings: Settings = Depends(get_settings),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
    deps: StockRecapDeps = Depends(_get_deps),
) -> StreamingResponse:
    """NDJSON 流：``meta`` → 各 ``phase`` → ``result``；进化与回测在流结束后执行。"""
    try:
        deps.guardrail.validate_generate_request(req)
    except GuardrailError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if deps.init_db is not None:
        deps.init_db(settings.db_path)
    ctx = RunContext.new(session_id=x_session_id)

    def body() -> Iterator[str]:
        yield from iter_generate_ndjson(
            req,
            settings,
            ctx=ctx,
            defer_evolution_backtest=True,
            guardrail=deps.guardrail,
            repo_factory=deps.repo_factory,
        )

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
