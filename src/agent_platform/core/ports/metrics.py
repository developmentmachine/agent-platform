"""Metrics port — decouples business code from runtime observability implementation.

Defines ``MetricsPort`` (the Protocol) and module-level convenience wrappers
that delegate to the runtime implementation via a configurable adapter.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class MetricsPort(Protocol):
    """Minimal metrics recording interface for recap phases."""

    def record_phase_duration(self, phase: str, duration_ms: float) -> None: ...
    def record_recap_run(self, mode: str, provider: str, status: str) -> None: ...


# ── Module-level adapter plumbing ──────────────────────────────────────────

_adapter: Optional[MetricsPort] = None


def configure_metrics_port(port: MetricsPort) -> None:
    """Register a concrete MetricsPort (called once at startup)."""
    global _adapter
    _adapter = port


def _get_port() -> MetricsPort:
    if _adapter is not None:
        return _adapter
    # Fallback: import the default runtime implementation lazily.
    from agent_platform.core.runtime.metrics import (
        record_phase_duration as _rpd,
        record_recap_run as _rrr,
    )

    class _DefaultAdapter:
        def record_phase_duration(self, phase: str, duration_ms: float) -> None:
            _rpd(phase, duration_ms)

        def record_recap_run(self, mode: str, provider: str, status: str) -> None:
            _rrr(mode, provider, status)

    return _DefaultAdapter()


# ── Convenience wrappers (drop-in replacements for the old function imports) ─

def record_phase_duration(phase: str, duration_ms: float) -> None:
    """Record the wall-clock duration of a recap phase (milliseconds)."""
    _get_port().record_phase_duration(phase, duration_ms)


def record_recap_run(mode: str, provider: str, status: str) -> None:
    """Record a recap generate invocation (counter)."""
    _get_port().record_recap_run(mode, provider, status)


__all__ = [
    "MetricsPort",
    "configure_metrics_port",
    "record_phase_duration",
    "record_recap_run",
]
