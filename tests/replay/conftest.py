"""replay 子目录共享 fixture：注册 ``replay`` backend + 安装 ``ReplayProvider``。"""
from __future__ import annotations

import pytest

from agent_platform.domain.registries import (
    LlmBackendSpec,
    default_backend_registry,
)
from agent_platform.infra.llm.providers import (
    default_provider_registry,
    register_provider,
)
from agent_platform.agents.stock_recap.deps import configure_default_deps, reset_default_deps
from agent_platform.infra.persistence.factory import SqliteRepositoryFactory

from tests.replay._provider import ReplayProvider


class _NoopGuardrail:
    """Minimal GuardrailPort stub for replay tests."""
    def validate_generate_request(self, req): pass
    def validate_feedback_request(self, req): pass
    def pre_input(self, text, **kw): return text
    def post_output(self, text, **kw): return text
    def clamp_messages(self, msgs, **kw): return msgs
    def coerce_recap_output(self, recap, *a, **kw): return recap


@pytest.fixture
def replay_provider(tmp_path) -> ReplayProvider:
    """注册 ``replay`` 后端 + 实例 provider；测试结束后从注册表移除。"""
    backend_reg = default_backend_registry()
    if backend_reg.get("replay") is None:
        backend_reg.register(
            LlmBackendSpec(
                name="replay",
                display_name="Replay (test)",
                requires_api_key_env=None,
                supports_function_calling=False,
                aliases=("replay",),
            )
        )
    rp = ReplayProvider()
    register_provider("replay", rp)

    # Wire deps for stock_recap agent
    rf = SqliteRepositoryFactory(str(tmp_path / "replay_deps.db"))
    from agent_platform.infra.llm.backends import call_llm
    configure_default_deps(
        repo_factory=rf,
        guardrail=_NoopGuardrail(),
        llm_caller=lambda **kw: call_llm(**kw),
    )

    yield rp

    reset_default_deps()
    # cleanup：避免 provider 实例污染其他测试
    prov_reg = default_provider_registry()
    prov_reg._providers.pop("replay", None)  # noqa: SLF001
    backend_reg._specs.pop("replay", None)  # noqa: SLF001
    backend_reg._alias_to_name.pop("replay", None)  # noqa: SLF001
