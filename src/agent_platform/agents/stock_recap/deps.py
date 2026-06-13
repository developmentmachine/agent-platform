"""Dependency container for stock-recap agent.

Injects ports (RepositoryFactoryPort, GuardrailPort) and optional callables
so that business code never imports ``infra.*`` directly.

Usage::

    # Bootstrap (CLI / monolith entry point):
    from agent_platform.agents.stock_recap.deps import configure_default_deps
    configure_default_deps(
        repo_factory=SqliteRepositoryFactory(db_path),
        guardrail=GuardrailAdapter(),
        ...
    )

    # Business code:
    deps = default_deps()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from agent_platform.core.ports.memory import EmbeddingsPort, VectorStorePort
from agent_platform.core.ports.repository import RepositoryFactoryPort
from agent_platform.core.ports.guardrail import GuardrailPort

logger = logging.getLogger("agent_platform.agents.stock_recap.deps")


@dataclass
class StockRecapDeps:
    """All injectable dependencies for the stock-recap agent."""

    repo_factory: RepositoryFactoryPort
    guardrail: GuardrailPort

    # Optional callable factories — set by configure_default_deps().
    # Returns (EmbeddingsPort, VectorStorePort) for the memory vector stack.
    memory_factory: Optional[Callable[..., Tuple[EmbeddingsPort, VectorStorePort]]] = None
    # LLM caller: (settings, mode, messages, model_spec, ...) -> (Recap, LlmTokens)
    llm_caller: Optional[Callable[..., Any]] = None
    # Push provider factory: (settings, **kwargs) -> PushProvider | None
    push_provider_factory: Optional[Callable[..., Any]] = None
    # DB initializer: (db_path: str) -> None
    init_db: Optional[Callable[[str], None]] = None
    # Push test: (webhook_url: str) -> bool
    test_push: Optional[Callable[[str], bool]] = None


# Module-level singleton (lazy); configure_default_deps() populates it.
_default: Optional[StockRecapDeps] = None


def configure_default_deps(
    *,
    repo_factory: RepositoryFactoryPort,
    guardrail: GuardrailPort,
    memory_factory: Optional[Callable[..., Any]] = None,
    llm_caller: Optional[Callable[..., Any]] = None,
    push_provider_factory: Optional[Callable[..., Any]] = None,
    init_db: Optional[Callable[[str], None]] = None,
    test_push: Optional[Callable[[str], bool]] = None,
) -> None:
    """Called once at bootstrap to wire production implementations.

    Idempotent — calling again with the same arguments is a no-op.
    """
    global _default
    _default = StockRecapDeps(
        repo_factory=repo_factory,
        guardrail=guardrail,
        memory_factory=memory_factory,
        llm_caller=llm_caller,
        push_provider_factory=push_provider_factory,
        init_db=init_db,
        test_push=test_push,
    )
    logger.debug("stock_recap deps configured")


def default_deps() -> StockRecapDeps:
    """Return the configured deps singleton.

    Raises ``RuntimeError`` if ``configure_default_deps()`` has not been called
    by the bootstrap entry point.
    """
    if _default is not None:
        return _default
    raise RuntimeError(
        "Stock recap deps not configured. "
        "Call configure_default_deps() from the bootstrap entry point."
    )


def reset_default_deps() -> None:
    """Reset the cached default deps (for testing)."""
    global _default
    _default = None


__all__ = [
    "StockRecapDeps",
    "configure_default_deps",
    "default_deps",
    "reset_default_deps",
]
