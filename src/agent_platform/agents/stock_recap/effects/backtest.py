"""次日策略回测：生成 T+1 之后对比真实行情，落库 ``backtest_results``。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from agent_platform.core.utils import stable_json as _stable_json
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.domain.models import RecapStrategy
from agent_platform.agents.stock_recap.data.collector import collect_snapshot
from agent_platform.agents.stock_recap.llm.eval import compute_backtest

logger = logging.getLogger("agent_platform.side_effects.backtest")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")



def load_recent_backtests_simple(
    repo_factory: RepositoryFactoryPort, limit: int = 3
) -> List[dict]:
    """读取最近 N 条回测结果；任何异常（如表尚未创建）返回空列表。"""
    try:
        return repo_factory.backtest_repository().load_recent(limit=limit)
    except Exception:
        return []

def try_run_backtest(repo_factory: RepositoryFactoryPort, today: str) -> None:
    """如存在昨日 ``strategy`` 记录且未回测，则计算并落库。"""
    try:
        backtest_repo = repo_factory.backtest_repository()
        run_repo = repo_factory.run_repository()

        strategy_date = backtest_repo.get_pending(today=today)
        if strategy_date is None:
            return

        runs = run_repo.load_recent(date=today, mode="strategy", limit=1)
        if not runs or not runs[0].get("recap"):
            return

        recap_data = runs[0]["recap"]
        strategy_recap = RecapStrategy.model_validate(recap_data)

        today_snapshot = collect_snapshot("live", today, skip_trading_check=True)

        result = compute_backtest(
            strategy_date=strategy_date,
            strategy_recap=strategy_recap,
            actual_date=today,
            actual_snapshot=today_snapshot,
        )

        backtest_repo.insert(result=result, created_at=_utc_now_iso())
        logger.info(
            _stable_json(
                {
                    "event": "backtest_complete",
                    "strategy_date": strategy_date,
                    "hit_rate": result.hit_rate,
                }
            )
        )
    except Exception as e:
        logger.warning(_stable_json({"event": "backtest_failed", "error": str(e)}))
