"""W2: tools_server / InProcessMcpClient / McpToolGateway 单测。"""
from __future__ import annotations

import pytest

from agent_platform.config.settings import Settings
from agent_platform.core.ports.mcp_tool import McpClientPort, McpToolDescriptor, McpToolResult
from agent_platform.infra.mcp_client.inproc import InProcessMcpClient
from agent_platform.infra.guardrail.tools import ToolDisabled, ToolPolicy, ToolPolicyRegistry
from agent_platform.runtime.mcp_gateway import McpToolGateway
from agent_platform.tools_server.registry import (
    ToolRegistry,
    ToolSpec,
    build_default_registry,
)


# ─── tools_server.registry ───────────────────────────────────────────────────


def test_default_registry_exposes_three_builtin_tools() -> None:
    reg = build_default_registry()
    assert reg.names() == ["query_history", "query_market_data", "web_search"]
    web = reg.get("web_search")
    assert web.input_schema["required"] == ["query"]
    assert web.to_openai_function()["function"]["name"] == "web_search"


def test_tool_spec_to_openai_function_shape() -> None:
    spec = ToolSpec(
        name="dummy",
        description="d",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        handler=lambda x: x,
    )
    out = spec.to_openai_function()
    assert out["type"] == "function"
    assert out["function"]["parameters"]["required"] == ["x"]


# ─── InProcessMcpClient ──────────────────────────────────────────────────────


@pytest.fixture
def inproc_with_fake_registry() -> InProcessMcpClient:
    fake_reg = ToolRegistry([
        ToolSpec(
            name="echo",
            description="echo back",
            input_schema={"type": "object", "properties": {"v": {"type": "string"}}, "required": ["v"]},
            handler=lambda v: f"echo:{v}",
        ),
        ToolSpec(
            name="boom",
            description="always raises",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=lambda: (_ for _ in ()).throw(RuntimeError("kaboom")),
        ),
    ])
    return InProcessMcpClient(registry=fake_reg, server_id="test")


def test_inproc_list_tools_sync(inproc_with_fake_registry: InProcessMcpClient) -> None:
    descs = inproc_with_fake_registry.list_tools_sync()
    names = sorted(d.name for d in descs)
    assert names == ["boom", "echo"]
    assert all(isinstance(d, McpToolDescriptor) for d in descs)


def test_inproc_call_sync_ok(inproc_with_fake_registry: InProcessMcpClient) -> None:
    r = inproc_with_fake_registry.call_sync("echo", {"v": "hi"})
    assert not r.is_error
    assert r.content == "echo:hi"


def test_inproc_call_sync_bad_arguments(inproc_with_fake_registry: InProcessMcpClient) -> None:
    r = inproc_with_fake_registry.call_sync("echo", {"wrong_arg": 1})
    assert r.is_error
    assert r.meta["error_kind"] == "bad_arguments"


def test_inproc_call_sync_unknown_tool(inproc_with_fake_registry: InProcessMcpClient) -> None:
    r = inproc_with_fake_registry.call_sync("missing", {})
    assert r.is_error
    assert r.meta["error_kind"] == "not_registered"


def test_inproc_call_sync_runtime_error(inproc_with_fake_registry: InProcessMcpClient) -> None:
    r = inproc_with_fake_registry.call_sync("boom", {})
    assert r.is_error
    assert r.meta["error_kind"] == "runtime"


# ─── McpToolGateway ──────────────────────────────────────────────────────────


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path, **overrides) -> Settings:
    base = {
        "RECAP_TOOLS_ENABLED": "true",
        "RECAP_TOOLS_WEB_SEARCH": "true",
        "RECAP_TOOLS_MARKET_DATA": "true",
        "RECAP_TOOLS_HISTORY": "true",
        "RECAP_TOOL_AUDIT_ENABLED": "false",
        "RECAP_PRINCIPAL_ROLE": "user",
        "RECAP_DB_PATH": str(tmp_path / "g.db"),
    }
    for k, v in overrides.items():
        base[k] = str(v)
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    return Settings()


class _FakeClient(McpClientPort):
    """记录调用、返回预设结果的 MCP client 测试桩。"""

    def __init__(self, descriptors, content="ok"):
        self._descs = descriptors
        self.calls: list[tuple[str, dict]] = []
        self._content = content

    async def list_tools(self):
        return self._descs

    async def call(self, name, arguments, **kwargs):
        self.calls.append((name, arguments))
        return McpToolResult(name=name, content=self._content, is_error=False, meta={})

    async def close(self):
        return None

    def call_sync(self, name, arguments, *, timeout_s=None):
        self.calls.append((name, arguments))
        return McpToolResult(name=name, content=self._content, is_error=False, meta={})


def _descs(*names):
    return [
        McpToolDescriptor(
            name=n,
            description=n,
            input_schema={"type": "object", "properties": {}, "required": []},
            server_id="t",
            read_only=True,
        )
        for n in names
    ]


def test_gateway_openai_schemas_from_descriptors(monkeypatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path)
    client = _FakeClient(_descs("web_search", "query_market_data", "query_history"))
    gw = McpToolGateway(s, client)
    schemas = gw.openai_compatible_schemas()
    names = [x["function"]["name"] for x in schemas]
    assert sorted(names) == ["query_history", "query_market_data", "web_search"]
    assert all(x["type"] == "function" for x in schemas)


def test_gateway_filters_disabled_by_settings(monkeypatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path, RECAP_TOOLS_HISTORY="false")
    client = _FakeClient(_descs("web_search", "query_market_data", "query_history"))
    gw = McpToolGateway(s, client)
    assert "query_history" not in gw.enabled_tool_names()
    assert "web_search" in gw.enabled_tool_names()


def test_gateway_filters_unregistered_on_server(monkeypatch, tmp_path) -> None:
    """Policy 注册了 ``web_search``，但 MCP server 没有 — 应静默跳过。"""
    s = _settings(monkeypatch, tmp_path)
    client = _FakeClient(_descs("query_market_data"))
    gw = McpToolGateway(s, client)
    assert gw.enabled_tool_names() == {"query_market_data"}


def test_gateway_execute_disabled_raises_audit_off(monkeypatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path)
    client = _FakeClient(_descs("web_search"))
    reg = ToolPolicyRegistry()
    reg.register(ToolPolicy(name="web_search", enabled=False))
    gw = McpToolGateway(s, client, policy_registry=reg)
    with pytest.raises(ToolDisabled):
        gw.execute("web_search", {"query": "x"})
    assert client.calls == []


def test_gateway_execute_ok_calls_client(monkeypatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path)
    client = _FakeClient(_descs("web_search"), content="search-result")
    reg = ToolPolicyRegistry()
    reg.register(ToolPolicy(name="web_search"))
    gw = McpToolGateway(s, client, policy_registry=reg)
    out = gw.execute("web_search", {"query": "x"})
    assert out == "search-result"
    assert client.calls == [("web_search", {"query": "x"})]


# ─── 行为对齐：runtime.McpToolGateway ↔ infrastructure.tools.runner.RecapToolRunner ─


def test_runner_is_backed_by_mcp_gateway(monkeypatch, tmp_path) -> None:
    """W2: ``RecapToolRunner.openai_compatible_schemas`` 必须由 gateway 推导，
    而不是历史的 ``TOOL_SCHEMAS`` 硬编码常量。"""
    from agent_platform.infra.tools.runner import RecapToolRunner

    s = _settings(monkeypatch, tmp_path)
    runner = RecapToolRunner(s)
    schemas = runner.openai_compatible_schemas()
    names = {x["function"]["name"] for x in schemas}
    assert names == {"web_search", "query_market_data", "query_history"}
