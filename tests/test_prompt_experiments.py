"""Wave 4 / w4-4：``prompt_experiments`` + 分桶 + variant_id 落库。

覆盖：
1. ``select_variant`` 的稳定性（同 stickiness_key 落同 variant）+ 流量加权分布；
2. 没有 active 实验 / 没有 variants → 返回 None（不破坏主路径）；
3. 全链路：generate_once 命中实验 → ``recap_runs`` / ``recap_audit`` 落 experiment_id/variant_id；
4. ``/v1/experiments`` POST/GET 端点（API key 强校验、传 0 权重 400）。
"""
from __future__ import annotations

from typing import Counter, Optional

import pytest
from fastapi.testclient import TestClient

from agent_platform.agents.stock_recap.experiments import select_variant
from agent_platform.agents.stock_recap.deps import configure_default_deps, reset_default_deps
from agent_platform.infra.persistence.factory import SqliteRepositoryFactory
from agent_platform.config.settings import Settings
from agent_platform.infra.policy.guardrail_adapter import GuardrailAdapter
from agent_platform.infra.persistence.db import (
    get_conn,
    init_db,
    list_prompt_experiments,
    load_active_experiment,
    load_experiment_variants,
    upsert_prompt_experiment,
    upsert_prompt_experiment_variant,
)


_noop_guardrail = GuardrailAdapter


def _seed_experiment(
    db_path: str,
    *,
    experiment_id: str,
    mode: str,
    variants: list[tuple[str, str, int]],  # (variant_id, prompt_version, weight)
    status: str = "active",
) -> None:
    upsert_prompt_experiment(
        db_path,
        experiment_id=experiment_id,
        mode=mode,
        status=status,
        starts_at="2025-01-01T00:00:00+00:00",
        description="unit test",
        metadata={"owner": "test"},
        created_at="2025-01-01T00:00:00+00:00",
    )
    for v_id, pv, w in variants:
        upsert_prompt_experiment_variant(
            db_path,
            experiment_id=experiment_id,
            variant_id=v_id,
            prompt_version=pv,
            traffic_weight=w,
            metadata=None,
            created_at="2025-01-01T00:00:00+00:00",
        )


# ─── 1. select_variant：稳定性 + 加权分布 ─────────────────────────────


def test_select_variant_returns_none_when_no_experiment(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    rf = SqliteRepositoryFactory(settings.db_path)
    assert select_variant(rf, mode="daily", stickiness_key="abc") is None


def test_select_variant_returns_none_when_no_stickiness_key(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="e1",
        mode="daily",
        variants=[("A", "vA", 1), ("B", "vB", 1)],
    )
    rf = SqliteRepositoryFactory(settings.db_path)
    assert select_variant(rf, mode="daily", stickiness_key=None) is None
    assert select_variant(rf, mode="daily", stickiness_key="") is None


def test_select_variant_is_deterministic(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="e1",
        mode="daily",
        variants=[("A", "vA", 1), ("B", "vB", 1)],
    )
    rf = SqliteRepositoryFactory(settings.db_path)
    a1 = select_variant(rf, mode="daily", stickiness_key="user-42")
    a2 = select_variant(rf, mode="daily", stickiness_key="user-42")
    assert a1 is not None and a2 is not None
    assert a1.variant_id == a2.variant_id
    assert a1.prompt_version == a2.prompt_version


def test_select_variant_weight_distribution(fresh_settings):
    """权重 1:9 时，10000 个随机 key 中 B 占比应 > 80%。"""
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="e1",
        mode="daily",
        variants=[("A", "vA", 1), ("B", "vB", 9)],
    )
    rf = SqliteRepositoryFactory(settings.db_path)
    counter: Counter[str] = Counter()
    for i in range(10000):
        a = select_variant(
            rf, mode="daily", stickiness_key=f"k-{i}"
        )
        assert a is not None
        counter[a.variant_id] += 1
    # 1:9 加权 → 期望 B 90%；允许 ±10% 抖动
    total = sum(counter.values())
    ratio_b = counter["B"] / total
    assert 0.80 < ratio_b < 0.95, f"B ratio out of band: {ratio_b}"


def test_select_variant_zero_weight_excluded(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="e1",
        mode="daily",
        # B 权重为 0 应被 SQL 过滤掉，且 A 永远命中
        variants=[("A", "vA", 1), ("B", "vB", 0)],
    )
    rf = SqliteRepositoryFactory(settings.db_path)
    for i in range(50):
        a = select_variant(
            rf, mode="daily", stickiness_key=f"k-{i}"
        )
        assert a is not None
        assert a.variant_id == "A"


def test_select_variant_paused_experiment_ignored(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="e1",
        mode="daily",
        variants=[("A", "vA", 1)],
        status="paused",
    )
    rf = SqliteRepositoryFactory(settings.db_path)
    assert (
        select_variant(rf, mode="daily", stickiness_key="x") is None
    )


# ─── 2. CRUD 函数 ───────────────────────────────────────────────────────


def test_load_active_experiment_picks_latest_starts_at(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)

    upsert_prompt_experiment(
        settings.db_path,
        experiment_id="old",
        mode="daily",
        status="active",
        starts_at="2024-01-01T00:00:00+00:00",
        created_at="2024-01-01T00:00:00+00:00",
    )
    upsert_prompt_experiment(
        settings.db_path,
        experiment_id="new",
        mode="daily",
        status="active",
        starts_at="2025-06-01T00:00:00+00:00",
        created_at="2025-06-01T00:00:00+00:00",
    )
    active = load_active_experiment(settings.db_path, mode="daily")
    assert active is not None
    assert active["experiment_id"] == "new"


def test_list_prompt_experiments_filters(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    _seed_experiment(
        settings.db_path,
        experiment_id="d1",
        mode="daily",
        variants=[("A", "vA", 1)],
    )
    _seed_experiment(
        settings.db_path,
        experiment_id="s1",
        mode="strategy",
        variants=[("A", "vA", 1)],
    )
    items = list_prompt_experiments(settings.db_path, mode="daily")
    assert {i["experiment_id"] for i in items} == {"d1"}
    items = list_prompt_experiments(settings.db_path, status="active")
    assert {i["experiment_id"] for i in items} == {"d1", "s1"}


# ─── 3. 全链路：generate_once 落 experiment_id/variant_id ──────────────


def test_pipeline_persists_experiment_id_and_variant(_wire_stock_recap_deps):
    settings, rf = _wire_stock_recap_deps
    init_db(settings.db_path)

    # 单 variant 100% 流量，确保命中
    _seed_experiment(
        settings.db_path,
        experiment_id="exp-e2e",
        mode="daily",
        variants=[("only", "v-experiment", 1)],
    )

    from agent_platform.agents.stock_recap.use_case import generate_once
    from agent_platform.domain.models import GenerateRequest

    req = GenerateRequest(
        mode="daily",
        provider="mock",
        force_llm=False,
        skip_trading_check=True,
        session_id="user-sticky-1",
    )
    resp = generate_once(req, settings, repo_factory=rf)

    # recap_runs
    with get_conn(settings.db_path) as conn:
        row = conn.execute(
            "SELECT experiment_id, variant_id, prompt_version FROM recap_runs WHERE request_id=?",
            (resp.request_id,),
        ).fetchone()
    assert row is not None
    assert row["experiment_id"] == "exp-e2e"
    assert row["variant_id"] == "only"
    assert row["prompt_version"] == "v-experiment"

    # recap_audit 同步带上
    from agent_platform.infra.persistence.db import load_recap_audit

    audits = load_recap_audit(settings.db_path, request_id=resp.request_id)
    assert len(audits) == 1
    assert audits[0]["experiment_id"] == "exp-e2e"
    assert audits[0]["variant_id"] == "only"


def test_pipeline_no_experiment_keeps_global_prompt_version(_wire_stock_recap_deps):
    """当 mode 没有 active 实验时，experiment_id/variant_id 应为 NULL。"""
    settings, rf = _wire_stock_recap_deps
    init_db(settings.db_path)

    from agent_platform.agents.stock_recap.use_case import generate_once
    from agent_platform.domain.models import GenerateRequest

    req = GenerateRequest(
        mode="daily", provider="mock", force_llm=False, skip_trading_check=True
    )
    resp = generate_once(req, settings, repo_factory=rf)

    with get_conn(settings.db_path) as conn:
        row = conn.execute(
            "SELECT experiment_id, variant_id FROM recap_runs WHERE request_id=?",
            (resp.request_id,),
        ).fetchone()
    assert row["experiment_id"] is None
    assert row["variant_id"] is None


# ─── 4. /v1/experiments 端点 ───────────────────────────────────────────


def _client(settings: Settings) -> TestClient:
    from agent_platform.adapters.http.app import create_app

    app = create_app()
    return TestClient(app)


def test_experiments_endpoint_requires_api_key(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    client = _client(settings)
    # GET 与 POST 都需要 key
    assert client.get("/v1/experiments").status_code == 401
    assert client.post("/v1/experiments", json={}).status_code == 401


def test_experiments_endpoint_rejects_zero_weight_payload(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    client = _client(settings)
    headers = {"x-api-key": "test-key"}
    body = {
        "experiment_id": "e-zero",
        "mode": "daily",
        "status": "active",
        "variants": [
            {"variant_id": "A", "prompt_version": "vA", "traffic_weight": 0},
            {"variant_id": "B", "prompt_version": "vB", "traffic_weight": 0},
        ],
    }
    r = client.post("/v1/experiments", json=body, headers=headers)
    assert r.status_code == 400


def test_experiments_endpoint_upsert_then_list(fresh_settings):
    settings = fresh_settings
    init_db(settings.db_path)
    client = _client(settings)
    headers = {"x-api-key": "test-key"}

    body = {
        "experiment_id": "e-http",
        "mode": "daily",
        "status": "active",
        "description": "via http",
        "variants": [
            {"variant_id": "A", "prompt_version": "vA", "traffic_weight": 3},
            {"variant_id": "B", "prompt_version": "vB", "traffic_weight": 7},
        ],
    }
    r = client.post("/v1/experiments", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # 再 POST 一次（同 experiment_id）应该是幂等的
    r = client.post("/v1/experiments", json=body, headers=headers)
    assert r.status_code == 200

    r = client.get("/v1/experiments?mode=daily", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["experiment_id"] == "e-http"
    variant_ids = {v["variant_id"] for v in item["variants"]}
    assert variant_ids == {"A", "B"}
