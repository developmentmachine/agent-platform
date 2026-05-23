"""W6: 验证 CLI / HTTP / Scheduler 全部按 ``AgentRegistry`` 自动装配。"""
from __future__ import annotations

from typing import List

import pytest


def _reset_registry():
    from agent_platform.core.registry.agent_registry import get_default_registry

    get_default_registry().clear()


# ─── HTTP：app 自动 include 各 Agent 路由 ──────────────────────────────────────


def test_http_app_auto_includes_recap_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_registry()
    from agent_platform.adapters.http.api.app import create_app

    app = create_app()
    paths = {route.path for route in app.router.routes}
    # recap 自带路由（来自 manifest.http_router_factories）
    assert "/v1/recap" in paths
    assert "/v1/recap/stream" in paths
    assert "/v1/feedback" in paths
    # 平台公共路由（与 Agent 无关）仍存在
    assert "/healthz" in paths


# ─── CLI：自动发现子命令 + --list-agents ────────────────────────────────────


def test_cli_list_agents_includes_stock_recap(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _reset_registry()
    from agent_platform.adapters.cli import main as cli_mod

    monkeypatch.setattr("sys.argv", ["agent_platform", "--list-agents"])
    rc = cli_mod.cli_main()
    assert rc == 0
    captured = capsys.readouterr().out
    assert "stock-recap" in captured
    assert "report" in captured  # AgentCapability.REPORT 展示


def test_cli_subparser_registered_for_each_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """通过模拟 ``--help`` 触发 subparser 装配。"""
    _reset_registry()
    from agent_platform.adapters.cli import main as cli_mod

    monkeypatch.setattr("sys.argv", ["agent_platform", "stock-recap", "--help"])
    with pytest.raises(SystemExit) as ei:
        cli_mod.cli_main()
    assert ei.value.code == 0  # --help 正常退出


# ─── Scheduler：自动绑定 ScheduledJob ──────────────────────────────────────────


def test_scheduler_auto_binds_agent_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _reset_registry()
    from apscheduler.schedulers.background import BackgroundScheduler

    started: List[bool] = []

    real_init = BackgroundScheduler.__init__
    real_add = BackgroundScheduler.add_job

    captured_jobs: List[dict] = []

    def _capture_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)

    def _capture_add(self, fn, trigger, **kwargs):
        captured_jobs.append({"id": kwargs.get("id"), "trigger": type(trigger).__name__})
        return real_add(self, fn, trigger, **kwargs)

    monkeypatch.setattr(BackgroundScheduler, "__init__", _capture_init)
    monkeypatch.setattr(BackgroundScheduler, "add_job", _capture_add)

    # 阻止真的启动 + 阻止真的执行任务
    monkeypatch.setattr(
        BackgroundScheduler, "start", lambda self, *a, **kw: started.append(True)
    )

    from agent_platform.config.settings import Settings
    from agent_platform.adapters.scheduler.jobs import start_scheduler

    monkeypatch.setenv("RECAP_DB_PATH", str(tmp_path / "sched.db"))
    monkeypatch.setenv("RECAP_OUTBOX_SWEEP_INTERVAL_SECONDS", "60")
    settings = Settings()

    start_scheduler(settings)
    assert started

    ids = [j["id"] for j in captured_jobs]
    # 平台公共
    assert "outbox_sweep" in ids
    # Agent 自带（stock-recap manifest 声明的 3 个）
    assert "stock-recap.stock_recap.daily" in ids
    assert "stock-recap.stock_recap.strategy" in ids
    assert "stock-recap.stock_recap.backtest" in ids
    # 所有 agent job 必须用 CronTrigger
    for job in captured_jobs:
        if job["id"].startswith("stock-recap."):
            assert job["trigger"] == "CronTrigger"
