"""AgentRegistry + discovery 基本行为。"""
from __future__ import annotations

from pydantic import BaseModel

from agent_platform.core.errors import AgentNotFound
from agent_platform.core.registry import (
    AgentCapability,
    AgentDefinition,
    AgentRegistry,
)
from agent_platform.core.registry.agent_registry import discover_agents


class _Req(BaseModel):
    x: int = 0


class _Resp(BaseModel):
    y: int = 0


def _defn(agent_id: str = "demo") -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        display_name="demo",
        description="demo",
        request_model=_Req,
        response_model=_Resp,
        capabilities=[AgentCapability.CHAT],
        chat_handler=lambda **kwargs: _Resp(y=42),
    )


def test_register_and_get():
    reg = AgentRegistry()
    reg.register(_defn("a"))
    assert reg.has("a")
    assert reg.get("a").id == "a"


def test_get_missing_raises():
    reg = AgentRegistry()
    try:
        reg.get("missing")
    except AgentNotFound:
        return
    raise AssertionError("AgentNotFound expected")


def test_register_overrides_same_id():
    reg = AgentRegistry()
    reg.register(_defn("a"))
    reg.register(_defn("a"))
    assert reg.ids() == ["a"]


def test_discover_via_entry_points_is_idempotent():
    """``discover_agents`` 是幂等的：多次调用同一进程内 entry points 不应抛错。"""
    reg = AgentRegistry()
    discover_agents(reg)  # 不应抛
    discover_agents(reg)
    # 仓库自带 stock-recap entry point，但 editable install 下未必生效；
    # 仅断言函数本身不崩，名称由具体安装环境决定。
