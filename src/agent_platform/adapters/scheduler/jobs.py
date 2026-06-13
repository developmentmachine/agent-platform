"""APScheduler 调度层 — W6 起按 ``AgentRegistry`` 自动绑定 cron。

设计：
- 平台只维护 1 个跨 Agent 公共任务 ``outbox_sweep``；
- 其他所有调度任务由各 Agent 在 manifest 中声明 ``scheduled_jobs``，本模块迭代
  ``AgentRegistry`` 自动 ``add_job(handler, CronTrigger(**cron_kwargs))``；
- 新 Agent 接入调度时无需修改平台代码。
"""
from __future__ import annotations

import json
import logging
from typing import Any, List

from agent_platform.core.utils import stable_json as _stable_json
from agent_platform.core.utils import logged_errors as _logged_errors
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agent_platform.application.side_effects import outbox
from agent_platform.config.settings import Settings
from agent_platform.core.registry.agent_definition import ScheduledJob

logger = logging.getLogger("agent_platform.scheduler")




def _on_sweep_success(summary: Any) -> dict | None:
    if not summary.claimed:
        return None
    return {
        "event": "scheduler_outbox_sweep",
        "claimed": summary.claimed,
        "done": summary.done,
        "failed_retry": summary.failed_retry,
        "failed_final": summary.failed_final,
    }

def _on_sweep_error(exc: Exception) -> dict:
    return {"job": "outbox"}

@_logged_errors(
    "scheduler_error",
    reraise=False,
    on_success=_on_sweep_success,
    on_error=_on_sweep_error,
    logger_name="agent_platform.scheduler",
)
def _run_outbox_sweep(settings: Settings) -> None:
    """周期 sweep outbox：兜底 ``BackgroundTasks`` 没消费成功的任务。

    与交易日无关 —— 失败重试可能跨日。单次最多处理 32 条；正常负载下完全够用，
    且不会让一次 sweep 拖太久。
    """
    outbox.process_due(settings.db_path, batch=32)


def _load_registry():
    """触发 entry_points 发现所有 Agent。"""
    from agent_platform.core.registry.agent_registry import (
        discover_agents,
        get_default_registry,
    )

    reg = get_default_registry()
    discover_agents(reg)
    return reg


def _collect_agent_jobs() -> List[tuple[str, ScheduledJob]]:
    """从 AgentRegistry 收集所有 ``ScheduledJob``，返回 ``[(agent_id, job)]``。"""
    out: List[tuple[str, ScheduledJob]] = []
    for defn in _load_registry().list():
        for job in defn.scheduled_jobs:
            out.append((defn.id, job))
    return out


def start_scheduler(settings: Settings) -> Any:
    """
    创建并启动 APScheduler BackgroundScheduler。

    任务来源：
    - 平台公共：``outbox_sweep``（IntervalTrigger）；
    - Agent 自带：每个 ``AgentDefinition.scheduled_jobs`` 中的 ``ScheduledJob``
      经 ``CronTrigger(**cron_kwargs)`` 自动注册，id = ``"{agent_id}.{job.id}"``。
    """
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    # ── 平台公共 ────────────────────────────────────────────────────────
    scheduler.add_job(
        _run_outbox_sweep,
        IntervalTrigger(seconds=max(15, int(settings.outbox_sweep_interval_seconds))),
        id="outbox_sweep",
        args=[settings],
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # ── Agent 自带（按 Registry 自动装配） ─────────────────────────────
    registered_ids: List[str] = []
    for agent_id, job in _collect_agent_jobs():
        job_id = f"{agent_id}.{job.id}" if not job.id.startswith(agent_id) else job.id
        try:
            scheduler.add_job(
                job.handler,
                CronTrigger(**job.cron_kwargs),
                id=job_id,
                args=[settings],
                coalesce=job.coalesce,
                max_instances=job.max_instances,
                replace_existing=job.replace_existing,
            )
            registered_ids.append(job_id)
        except Exception as e:
            logger.error(
                _stable_json(
                    {
                        "event": "scheduler_job_register_failed",
                        "agent_id": agent_id,
                        "job_id": job_id,
                        "error": str(e),
                    }
                )
            )

    scheduler.start()
    logger.info(
        _stable_json(
            {
                "event": "scheduler_started",
                "agent_jobs": registered_ids,
                "outbox_sweep_seconds": int(settings.outbox_sweep_interval_seconds),
            }
        )
    )
    return scheduler
