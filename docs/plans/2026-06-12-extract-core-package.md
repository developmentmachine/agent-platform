# Extract `agent-platform-core` Package

**Goal:** Split `domain/`, `config/`, `core/` into a standalone `agent-platform-core` package with zero platform dependencies.

**Architecture:** Monorepo with two packages under `packages/core/`. The core installs as `agent_platform_core`, with compatibility shims in the main package so existing `from agent_platform.domain import ...` still works.

## Dependency Graph (Before → After)

**Before:** `core` → `runtime.observability.runtime_context` (circular with `runtime` → `core`)
**After:** `runtime` → `core` (one-way). ContextVars live in `core.runtime.contextvars`.

## Step 1: Move ContextVar definitions into core

Move `current_run_context` and `current_budget` from `src/agent_platform/runtime/observability/runtime_context.py` into `src/agent_platform/core/runtime/contextvars.py`.

- `core/runtime/contextvars.py` — becomes the **canonical source** for all 4 ContextVars
- `runtime/observability/runtime_context.py` — becomes a **re-export shim** pointing to core

## Step 2: Create packages/core/ directory structure

```
packages/core/
├── pyproject.toml
└── src/
    └── agent_platform_core/
        ├── __init__.py
        ├── domain/
        │   ├── __init__.py
        │   ├── models.py
        │   ├── run_context.py
        │   ├── backtest_strategy.py
        │   ├── data_providers.py
        │   ├── principal.py
        │   ├── registries.py
        │   └── repositories.py
        ├── config/
        │   ├── __init__.py
        │   └── settings.py
        └── core/
            ├── __init__.py
            ├── errors.py
            ├── http.py
            ├── services.py
            ├── utils.py
            ├── orchestration/
            ├── ports/
            ├── registry/
            └── runtime/
```

## Step 3: Create pyproject.toml for core

Minimal deps: `pydantic`, `pydantic-settings`, `fastapi` (for http.py).

## Step 4: Create compatibility shims in main package

Replace each moved module with a thin re-export:
```python
# src/agent_platform/domain/__init__.py
from agent_platform_core.domain import *
```

## Step 5: Update main pyproject.toml

Add `agent-platform-core` as dependency.

## Step 6: Run tests to verify

```bash
cd /opt/data/agent-platform && PYTHONPATH=src:packages/core/src pytest tests/ -x -q
```
