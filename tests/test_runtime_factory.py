"""create_runtime 装配链路最小验证。"""
from __future__ import annotations

from agent_platform.core.registry import AgentRegistry
from agent_platform.runtime import create_runtime


def test_create_runtime_registers_stock_recap():
    registry = AgentRegistry()
    runtime = create_runtime(registry=registry, auto_discover=False)
    assert runtime.registry.has("stock-recap")
    defn = runtime.registry.get("stock-recap")
    assert defn.id == "stock-recap"
    assert defn.runner is not None
    assert "web_search" in defn.mcp_tool_names
    assert defn.skill_bundle == "stock-recap"
    assert "a_share.daily_recap" in defn.skills
    assert defn.skill_mode_map.get("daily") == "a_share.daily_recap"


def test_create_runtime_lists_agents():
    registry = AgentRegistry()
    runtime = create_runtime(registry=registry, auto_discover=False)
    ids = [a.id for a in runtime.list_agents()]
    assert "stock-recap" in ids
