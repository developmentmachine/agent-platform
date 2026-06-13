"""记忆管理 + 进化闭环。

核心功能：
1. load_recent_memory   — 取历史 recap 注入 LLM context
2. load_feedback_summary — 聚合用户反馈
3. extract_market_patterns — 用 LLM 提炼近期市场规律
4. run_evolution_cycle  — 高级进化：LLM 分析自身历史质量并产出改进建议

PROMPT_VERSION 管理：
- 基础版本来自 resources/prompts manifest（PROMPT_BASE_VERSION）
- 进化触发后，如 LLM 建议 bump，则自动递增 v1/v2/v3...
- ★ 活跃版本以 ``prompt_state`` 表（单行）为跨进程事实源；
  各 worker 只做短 TTL 的本地缓存，避免在 multi-worker 下漂移。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_platform.core.utils import logged_errors, resolve_from_context, stable_json as _stable_json
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.agents.stock_recap.llm.prompts import PROMPT_BASE_VERSION, pattern_extraction_system
from agent_platform.domain.models import EvolutionNote, Features, MarketSnapshot, Mode

logger = logging.getLogger("agent_platform.memory")

# ─── 本地 TTL 缓存（减少每次 /metrics、/healthz 对 DB 的查询） ────────────────────
_PROMPT_VERSION_CACHE_TTL_S = 5.0
_cache_lock = threading.Lock()
_cached_version: Optional[str] = None
_cached_factory_key: Optional[str] = None
_cached_at: float = 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _factory_cache_key(repo_factory: RepositoryFactoryPort) -> str:
    """Derive a stable cache key from a repository factory.

    For SqliteRepositoryFactory, uses ``db_path``; otherwise falls back to ``id()``.
    """
    return getattr(repo_factory, "db_path", None) or str(id(repo_factory))



# ─── PROMPT_VERSION 管理（DB 事实源 + 短 TTL 缓存） ──────────────────────────────

def _default_initial_version() -> str:
    return f"{PROMPT_BASE_VERSION}.v1"


@logged_errors("prompt_state_backfill_failed", reraise=False, logger_name="agent_platform.memory")
def _backfill_prompt_state(repo_factory: RepositoryFactoryPort, recovered: str) -> None:
    evo_repo = repo_factory.evolution_repository()
    evo_repo.set_active_prompt_version(recovered, updated_at=_utc_now_iso())


@logged_errors("prompt_state_init_failed", reraise=False, logger_name="agent_platform.memory")
def _init_prompt_state(repo_factory: RepositoryFactoryPort, initial: str) -> None:
    evo_repo = repo_factory.evolution_repository()
    evo_repo.set_active_prompt_version(initial, updated_at=_utc_now_iso())


def _resolve_prompt_version(repo_factory: RepositoryFactoryPort) -> str:
    """直接从 DB 解析活跃版本；prompt_state 为空则回退到最新 evolution_note，最后回退到 base 版本。"""
    evo_repo = repo_factory.evolution_repository()
    ver = evo_repo.get_active_prompt_version()
    if ver:
        return ver

    note = evo_repo.load_latest_note()
    if note and note.get("prompt_version_suggested"):
        recovered = note["prompt_version_suggested"]
        # 把老库的 evolution_notes 数据回填到 prompt_state，让后续访问走快路径
        _backfill_prompt_state(repo_factory, recovered)
        return recovered

    initial = _default_initial_version()
    _init_prompt_state(repo_factory, initial)
    return initial


def get_prompt_version(repo_factory: RepositoryFactoryPort) -> str:
    """获取当前活跃的 PROMPT_VERSION。

    线程安全；本地缓存 TTL=5s，过期后从 DB 重新解析；这保证：
    - 单 worker 下高频健康检查不会反复打 DB；
    - 多 worker 下 5s 内必定收敛到 DB 事实源。
    """
    global _cached_version, _cached_factory_key, _cached_at
    fkey = _factory_cache_key(repo_factory)

    now = time.monotonic()
    with _cache_lock:
        if (
            _cached_version is not None
            and _cached_factory_key == fkey
            and (now - _cached_at) < _PROMPT_VERSION_CACHE_TTL_S
        ):
            return _cached_version

    # 出锁后查 DB（避免 DB 慢时阻塞其他读者）
    version = _resolve_prompt_version(repo_factory)

    with _cache_lock:
        _cached_version = version
        _cached_factory_key = fkey
        _cached_at = time.monotonic()
    return version


def _bump_prompt_version(current: str) -> str:
    parts = current.rsplit(".v", 1)
    if len(parts) == 2:
        try:
            n = int(parts[1])
            return f"{parts[0]}.v{n + 1}"
        except ValueError:
            pass
    return current + ".v2"


def _set_prompt_version(repo_factory: RepositoryFactoryPort, version: str) -> None:
    """原子写入 prompt_state 并失效本地缓存。"""
    global _cached_version, _cached_factory_key, _cached_at
    fkey = _factory_cache_key(repo_factory)
    evo_repo = repo_factory.evolution_repository()
    evo_repo.set_active_prompt_version(version, updated_at=_utc_now_iso())
    with _cache_lock:
        _cached_version = version
        _cached_factory_key = fkey
        _cached_at = time.monotonic()
    logger.info(_stable_json({"event": "prompt_version_bumped", "new_version": version}))


def _invalidate_prompt_version_cache() -> None:
    """测试辅助：清空本地缓存，强制下次访问重新查 DB。"""
    global _cached_version, _cached_factory_key, _cached_at
    with _cache_lock:
        _cached_version = None
        _cached_factory_key = None
        _cached_at = 0.0


# ─── 基础记忆加载 ──────────────────────────────────────────────────────────────

def _current_tenant_id() -> Optional[str]:
    """从 ``current_principal`` / ``domain.principal`` 读取 tenant_id（不存在则 None）。

    单租户 / CLI / 周期任务保持 None 行为兼容；HTTP 请求经过 ``require_api_key`` 后会有值。
    """
    return resolve_from_context("tenant_id")


def load_recent_memory(
    repo_factory: RepositoryFactoryPort,
    date: str,
    mode: Mode,
    limit: int = 5,
    *,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """取历史 recap 列表注入 LLM context（仅取摘要，避免 prompt 过长）。"""
    effective_tenant = tenant_id if tenant_id is not None else _current_tenant_id()
    run_repo = repo_factory.run_repository()
    runs = run_repo.load_recent(date=date, mode=mode, limit=limit, tenant_id=effective_tenant)
    result = []
    for run in runs:
        recap = run.get("recap") or {}
        # 只保留关键字段，减少 token 消耗
        summary: Dict[str, Any] = {
            "date": run["date"],
            "mode": run["mode"],
            "prompt_version": run["prompt_version"],
        }
        if run["mode"] == "daily" and "sections" in recap:
            summary["conclusions"] = [
                {"title": s.get("title"), "core_conclusion": s.get("core_conclusion")}
                for s in recap.get("sections", [])
            ]
        elif run["mode"] == "strategy" and "mainline_focus" in recap:
            summary["mainline_focus"] = recap.get("mainline_focus", [])

        # 附加评测结果
        if run.get("eval"):
            summary["eval_ok"] = run["eval"].get("ok")

        result.append(summary)
    return result


# ─── 市场模式提炼 ─────────────────────────────────────────────────────────────

def extract_market_patterns(
    repo_factory: RepositoryFactoryPort,
    days: int,
    settings: Any,
    model_spec: Optional[str] = None,
) -> Optional[str]:
    """
    调用 LLM（小模型）从近 N 天复盘中提炼持续性市场规律。
    返回一段文字描述，注入当天 prompt 作为背景上下文。
    若提炼失败则返回 None（不阻断主流程）。

    路由策略：仅在『有效 backend = openai 且 openai_api_key 已配置』时尝试；
    其余情况（用户选了 gemini-cli/cursor-cli/ollama）直接跳过，避免无谓的
    『Model Not Exist』报错与重试浪费。
    """
    from agent_platform.core.config.resolve import llm_backend_effective

    eff_backend = llm_backend_effective(model_spec, settings)
    if eff_backend != "openai" or not getattr(settings, "openai_api_key", None):
        logger.info(_stable_json({
            "event": "pattern_extraction_skipped_backend",
            "backend": eff_backend,
        }))
        return None

    run_repo = repo_factory.run_repository()
    runs = run_repo.load_recent(date=_today_str(), mode="daily", limit=days, tenant_id=_current_tenant_id())
    if len(runs) < 3:
        return None  # 历史数据不足，不提炼

    summaries = []
    for run in runs:
        recap = run.get("recap") or {}
        if run["mode"] == "daily" and "sections" in recap:
            for sec in recap.get("sections", []):
                summaries.append(f"{run['date']} {sec.get('title')}: {sec.get('core_conclusion')}")

    if not summaries:
        return None

    messages = [
        {
            "role": "system",
            "content": pattern_extraction_system(),
        },
        {"role": "user", "content": "\n".join(summaries[-30:])},  # 最多取30条
    ]

    # 直接用 openai 原始调用（不走 Recap schema 校验）
    try:
        import httpx
        from openai import OpenAI

        if not settings.openai_api_key:
            return None

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        resp = client.chat.completions.create(
            model=settings.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.3,
            max_tokens=400,
            timeout=30,
        )
        pattern_text = (resp.choices[0].message.content or "").strip()
        if pattern_text:
            logger.info(_stable_json({"event": "patterns_extracted", "chars": len(pattern_text)}))
            return pattern_text
    except Exception as e:
        logger.warning(_stable_json({"event": "pattern_extraction_failed", "error": str(e)}))

    return None

def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

# ─── 进化注入（读取最新笔记注入 system prompt） ──────────────────────────────────

def load_evolution_guidance(repo_factory: RepositoryFactoryPort) -> Optional[str]:
    """读取最新进化笔记，提炼为可注入 system prompt 的指导文字。"""
    evo_repo = repo_factory.evolution_repository()
    note = evo_repo.load_latest_note()
    if not note:
        return None
    notes_data = note.get("notes") or {}
    parts = []
    if notes_data.get("problems"):
        parts.append("【需要改进】" + "；".join(notes_data["problems"][:3]))
    if notes_data.get("prompt_suggestions"):
        parts.append("【写作建议】" + "；".join(notes_data["prompt_suggestions"][:3]))
    if notes_data.get("praised_patterns"):
        parts.append("【请保持】" + "；".join(notes_data["praised_patterns"][:2]))
    return "\n".join(parts) if parts else None


# ─── 进化循环（核心） ─────────────────────────────────────────────────────────

def check_and_run_evolution(
    repo_factory: RepositoryFactoryPort,
    settings: Any,
    trigger_run_id: Optional[str] = None,
    force: bool = False,
    model_spec: Optional[str] = None,
) -> Optional[str]:
    """
    检查是否满足进化触发条件，若满足则运行一次进化分析。

    触发条件（满足任一）：
    1. force=True（手动触发）
    2. 收到低评分（调用方判断后 force=True 传入）
    3. 自上次进化后累计新运行次数 >= evolution_min_runs

    返回：新的 prompt_version（如有版本升级），否则返回 None。
    """
    if not settings.evolution_enabled:
        return None

    # 进化目前完全依赖 OpenAI structured outputs（client.beta.chat.completions.parse），
    # 当用户主动选择非 openai backend 时直接跳过，避免 'Model Not Exist' 多次重试浪费。
    from agent_platform.core.config.resolve import llm_backend_effective

    eff_backend = llm_backend_effective(model_spec, settings)
    if eff_backend != "openai" or not getattr(settings, "openai_api_key", None):
        logger.info(_stable_json({
            "event": "evolution_skipped_backend",
            "backend": eff_backend,
        }))
        return None

    if not force:
        run_repo = repo_factory.run_repository()
        since_last = run_repo.count_since_last_evolution()
        if since_last < settings.evolution_min_runs:
            logger.debug(
                _stable_json(
                    {
                        "event": "evolution_skipped",
                        "since_last": since_last,
                        "threshold": settings.evolution_min_runs,
                    }
                )
            )
            return None

    logger.info(_stable_json({"event": "evolution_started", "trigger": trigger_run_id}))
    return _run_evolution(repo_factory, settings, trigger_run_id)


@logged_errors("evolution_failed", reraise=False, logger_name="agent_platform.memory")
def _run_evolution(
    repo_factory: RepositoryFactoryPort,
    settings: Any,
    trigger_run_id: Optional[str],
) -> Optional[str]:
    """实际执行进化分析：调用 LLM 分析历史质量，产出 EvolutionNote。"""
    from openai import OpenAI

    run_repo = repo_factory.run_repository()
    feedback_repo = repo_factory.feedback_repository()
    evo_repo = repo_factory.evolution_repository()

    runs = run_repo.load_for_evolution(limit=20)
    feedback_summary = feedback_repo.load_summary(limit=30)
    evo_history = evo_repo.load_history(limit=3)

    if not runs:
        logger.info(_stable_json({"event": "evolution_no_data"}))
        return None

    # 构建分析上下文
    analysis_context = {
        "recent_runs": [
            {
                "date": r["date"],
                "mode": r["mode"],
                "rating": r.get("rating"),
                "tags": r.get("tags", []),
                "comment": r.get("comment") or "",
                "eval_ok": (r.get("eval") or {}).get("ok"),
                "recap_summary": _recap_summary(r.get("recap")),
            }
            for r in runs
        ],
        "feedback_summary": feedback_summary,
        "previous_evolution_notes": [
            e.get("notes", {}).get("summary", "")
            for e in evo_history
        ],
    }

    system_prompt = (
        "你是一个专业的AI系统质量分析师，负责分析A股复盘智能体的历史输出质量并提出改进建议。\n"
        "请基于提供的历史运行记录（含用户评分和反馈）进行分析，输出严格符合 schema 的 JSON。\n"
        "分析要具体可操作，不要泛泛而谈。"
    )

    user_prompt = _stable_json(
        {
            "task": "分析以下历史复盘数据，产出质量改进建议",
            "context": analysis_context,
            "output_schema": EvolutionNote.model_json_schema(),
            "instruction": "仅返回 JSON，不包含任何解释文字或 markdown 代码块",
        }
    )

    if not settings.openai_api_key:
        logger.warning(_stable_json({"event": "evolution_no_api_key"}))
        return None

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    try:
        resp = client.beta.chat.completions.parse(
            model=settings.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EvolutionNote,  # type: ignore[arg-type]
            temperature=0.3,
            timeout=60,
        )
        note = resp.choices[0].message.parsed
    except Exception as e:
        logger.warning(_stable_json({"event": "evolution_llm_failed", "error": str(e)}))
        # 降级：普通 JSON 解析
        try:
            resp2 = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                timeout=60,
            )
            content = resp2.choices[0].message.content or "{}"
            data = json.loads(content)
            note = EvolutionNote.model_validate(data)
        except Exception as e2:
            logger.warning(_stable_json({"event": "evolution_fallback_failed", "error": str(e2)}))
            return None

    current_version = get_prompt_version(repo_factory)
    new_version = _bump_prompt_version(current_version) if note.should_bump_version else None
    suggested_version = new_version or current_version

    evo_repo.insert_note(
        created_at=_utc_now_iso(),
        trigger_run_id=trigger_run_id,
        note=note,
        prompt_version_suggested=suggested_version,
    )

    if new_version:
        _set_prompt_version(repo_factory, new_version)
        logger.info(
            _stable_json(
                {
                    "event": "evolution_complete",
                    "version_bumped": True,
                    "new_version": new_version,
                    "summary": note.summary[:100],
                }
            )
        )
        return new_version
    else:
        logger.info(
            _stable_json(
                {
                    "event": "evolution_complete",
                    "version_bumped": False,
                    "summary": note.summary[:100],
                }
            )
        )
        return None


def _recap_summary(recap: Optional[Dict[str, Any]]) -> str:
    """从 recap dict 提取简短摘要（避免传太多 token 给进化分析）。"""
    if not recap:
        return ""
    mode = recap.get("mode", "")
    if mode == "daily":
        sections = recap.get("sections", [])
        return " | ".join(
            s.get("core_conclusion", "") for s in sections[:3]
        )
    elif mode == "strategy":
        focus = recap.get("mainline_focus", [])
        return "主线: " + ", ".join(focus[:5])
    return ""
