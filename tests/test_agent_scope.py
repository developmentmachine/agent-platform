"""AgentScope：运行期 MCP / skill 按 Agent 裁剪。"""
from __future__ import annotations

import pytest

from agent_platform.agents.stock_recap.manifest import _build_definition
from agent_platform.config.settings import Settings
from agent_platform.core.registry import AgentRegistry
from agent_platform.core.runtime.agent_scope import AgentScope, current_agent_scope, resolve_skill_id_for_agent
from agent_platform.infra.mcp_client.inproc import InProcessMcpClient
from agent_platform.infrastructure.tools.runner import RecapToolRunner
from agent_platform.policy.tools import ToolForbidden
from agent_platform.runtime import create_runtime
from agent_platform.runtime.mcp_gateway import McpToolGateway
from agent_platform.runtime.scope import agent_execution
from agent_platform.skills.loader import load_skill_overlay_for_mode, resolve_skill_id_for_mode


@pytest.fixture
def tools_enabled_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    for key, val in {
        "RECAP_TOOLS_ENABLED": "true",
        "RECAP_TOOLS_WEB_SEARCH": "true",
        "RECAP_TOOLS_MARKET_DATA": "true",
        "RECAP_TOOLS_HISTORY": "true",
        "RECAP_TOOL_AUDIT_ENABLED": "false",
        "RECAP_DB_PATH": str(tmp_path / "scope.db"),
    }.items():
        monkeypatch.setenv(key, val)
    return Settings()


def test_mcp_gateway_filters_by_agent_scope(tools_enabled_settings: Settings):
    gw = McpToolGateway(tools_enabled_settings, InProcessMcpClient())
    defn = _build_definition()
    with agent_execution(defn):
        assert gw.enabled_tool_names() == set(defn.mcp_tool_names)


def test_mcp_execute_forbidden_when_agent_has_no_tools(tools_enabled_settings: Settings):
    runner = RecapToolRunner(tools_enabled_settings)
    scope = AgentScope(
        agent_id="hsk30-tutor",
        mcp_tool_names=frozenset(),
        skill_ids=frozenset(),
        skill_mode_map={},
    )
    token = current_agent_scope.set(scope)
    try:
        with pytest.raises(ToolForbidden):
            runner.execute("web_search", {"query": "x"}, "test.db")
    finally:
        current_agent_scope.reset(token)


def test_skill_overlay_requires_agent_scope():
    with pytest.raises(RuntimeError, match="AgentScope"):
        load_skill_overlay_for_mode("daily")


def test_skill_overlay_uses_agent_mode_map():
    defn = _build_definition()
    scope = AgentScope.from_definition(defn)
    with agent_execution(defn):
        assert resolve_skill_id_for_agent(scope, "daily") == "a_share.daily_recap"
        doc = load_skill_overlay_for_mode("daily")
        assert doc is not None


def test_create_runtime_stock_recap_tools_match_declaration(tools_enabled_settings: Settings):
    reg = AgentRegistry()
    runtime = create_runtime(
        registry=reg,
        settings=tools_enabled_settings,
        auto_discover=False,
    )
    defn = runtime.registry.get("stock-recap")
    with agent_execution(defn):
        runner = RecapToolRunner(runtime.settings)
        assert runner.enabled_tool_names() == set(defn.mcp_tool_names)
