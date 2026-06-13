"""用户反馈：落库 + 条件触发进化循环。"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from agent_platform.agents.stock_recap.deps import StockRecapDeps, default_deps
from agent_platform.agents.stock_recap.memory.manager import check_and_run_evolution
from agent_platform.config.settings import Settings, get_settings
from agent_platform.domain.models import FeedbackRequest
from agent_platform.domain.principal import PrincipalContext
from agent_platform.core.http import require_api_key
from agent_platform.core.utils import stable_json, utc_now_iso
from agent_platform.core.ports.guardrail import GuardrailError, GuardrailPort

logger = logging.getLogger("agent_platform.adapters.http.feedback")

router = APIRouter(tags=["recap"])


def _get_deps() -> StockRecapDeps:
    return default_deps()


@router.post("/v1/feedback")
def api_feedback(
    req: FeedbackRequest,
    settings: Settings = Depends(get_settings),
    principal: PrincipalContext = Depends(require_api_key),
    deps: StockRecapDeps = Depends(_get_deps),
) -> Dict[str, Any]:
    try:
        deps.guardrail.validate_feedback_request(req)
    except GuardrailError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if deps.init_db is not None:
        deps.init_db(settings.db_path)
    feedback_repo = deps.repo_factory.feedback_repository()
    feedback_repo.insert(
        request_id=req.request_id,
        rating=int(req.rating),
        tags=req.tags,
        comment=req.comment,
        created_at=utc_now_iso(),
        tenant_id=principal.tenant_id,
    )

    force = req.rating <= 2
    if force:
        logger.info(stable_json({"event": "low_rating_evolution", "rating": req.rating}))
    evolved = check_and_run_evolution(
        deps.repo_factory,
        settings=settings,
        trigger_run_id=req.request_id,
        force=force,
    )

    return {
        "ok": True,
        "evolved": evolved is not None,
        "new_prompt_version": evolved,
    }
