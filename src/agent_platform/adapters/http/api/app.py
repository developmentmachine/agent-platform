"""FastAPI 应用工厂。

装配步骤：
1. ``create_app()`` 建立 FastAPI 实例并绑定 lifespan（启动时 configure_tracing）；
2. 安装 middleware（CORS 按配置条件挂载）；
3. 挂载各 ``v1/*`` 子路由。

``interfaces/api/routes.py`` 只做一件事：``app = create_app()`` 暴露 uvicorn 入口。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from agent_platform.config.settings import get_settings
from agent_platform.adapters.http.api.middleware import install_cors
from agent_platform.adapters.http.api.v1 import jobs_router, ops_router


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    import logging

    from agent_platform.observability.logging_setup import setup_structured_logging
    from agent_platform.observability.tracing import configure_tracing

    setup_structured_logging(level=logging.INFO)
    configure_tracing(get_settings())
    yield


def _load_registry():
    """触发 builtin agent 注册 + entry_points 发现。

    HTTP 入口可以在 ``app.include_router`` 之前安全调用 — 不会启动事件循环。
    """
    from agent_platform.agents.stock_recap import manifest as stock_recap_manifest
    from agent_platform.core.registry.agent_registry import (
        discover_agents,
        get_default_registry,
    )

    reg = get_default_registry()
    if not reg.has(stock_recap_manifest.AGENT_ID):
        stock_recap_manifest.register(reg)
    discover_agents(reg)
    return reg


def create_app() -> FastAPI:
    from fastapi import Response
    from fastapi.responses import RedirectResponse

    app = FastAPI(
        title="Agent Platform API",
        description=(
            "多 Agent 平台统一 HTTP 入口。每个 Agent 在 manifest 中声明 "
            "``http_router_factories``，由本工厂迭代 ``AgentRegistry`` 自动挂载。"
        ),
        version="2.0.0",
        lifespan=_app_lifespan,
    )
    install_cors(app)

    # ── 平台级公共路由（与具体 Agent 无关） ─────────────────────────────
    app.include_router(ops_router)
    app.include_router(jobs_router)

    # ── Agent 自带路由（W6: 按 AgentRegistry 自动装配） ─────────────────
    # 每个 factory 可以返回单个 APIRouter，也可以返回 list[APIRouter]；都按顺序挂载。
    registry = _load_registry()
    for defn in registry.list():
        for factory in defn.http_router_factories:
            try:
                produced = factory()
            except Exception:
                import logging

                logging.getLogger("agent_platform.adapters.http.api.app").exception(
                    "agent http router factory failed: agent=%s", defn.id
                )
                continue
            routers = produced if isinstance(produced, list) else [produced]
            for router in routers:
                app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(content=b"", media_type="image/x-icon")

    return app
