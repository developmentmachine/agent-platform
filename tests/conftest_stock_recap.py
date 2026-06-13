"""Shared fixtures for stock_recap tests — wires default_deps with test stubs."""
from __future__ import annotations

import pytest

from agent_platform.agents.stock_recap.deps import (
    StockRecapDeps,
    configure_default_deps,
    reset_default_deps,
)
from agent_platform.core.ports.guardrail import GuardrailPort
from agent_platform.core.ports.repository import RepositoryFactoryPort


class _NoopGuardrail:
    """Minimal GuardrailPort stub for tests that don't exercise guardrails."""
    def validate_generate_request(self, req):  # noqa: ANN001
        pass
    def validate_feedback_request(self, req):  # noqa: ANN001
        pass


@pytest.fixture(autouse=False)
def _configure_stock_recap_deps():
    """Auto-configure stock_recap default_deps for tests that need it.

    NOT autouse — only tests that explicitly request this fixture get wired.
    """
    configure_default_deps(
        repo_factory=None,  # type: ignore[arg-type]  # tests pass repo_factory per-call
        guardrail=_NoopGuardrail(),  # type: ignore[arg-type]
    )
    yield
    reset_default_deps()
