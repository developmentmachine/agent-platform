#!/bin/bash
set -e

cd /opt/data/agent-platform

echo "=== Step 1: Verify shim files are already deleted ==="
count=$(find src/agent_platform/core/ src/agent_platform/domain/ src/agent_platform/config/ -name '*.py' -not -path '*__pycache__*' | wc -l)
echo "Remaining .py files in shim dirs: $count"

echo "=== Step 2: Copying real source files ==="
# Ensure destination directories exist
mkdir -p src/agent_platform/core/ports
mkdir -p src/agent_platform/core/runtime
mkdir -p src/agent_platform/core/orchestration
mkdir -p src/agent_platform/core/registry
mkdir -p src/agent_platform/core/config
mkdir -p src/agent_platform/domain
mkdir -p src/agent_platform/config

# Copy core/** -> src/agent_platform/core/**
cp packages/core/src/agent_platform_core/core/__init__.py src/agent_platform/core/__init__.py
cp packages/core/src/agent_platform_core/core/utils.py src/agent_platform/core/utils.py
cp packages/core/src/agent_platform_core/core/services.py src/agent_platform/core/services.py
cp packages/core/src/agent_platform_core/core/http.py src/agent_platform/core/http.py
cp packages/core/src/agent_platform_core/core/errors.py src/agent_platform/core/errors.py

# ports/
for f in packages/core/src/agent_platform_core/core/ports/*.py; do
  cp "$f" src/agent_platform/core/ports/
done

# runtime/
for f in packages/core/src/agent_platform_core/core/runtime/*.py; do
  cp "$f" src/agent_platform/core/runtime/
done

# orchestration/
for f in packages/core/src/agent_platform_core/core/orchestration/*.py; do
  cp "$f" src/agent_platform/core/orchestration/
done

# registry/
for f in packages/core/src/agent_platform_core/core/registry/*.py; do
  cp "$f" src/agent_platform/core/registry/
done

# config/
for f in packages/core/src/agent_platform_core/core/config/*.py; do
  cp "$f" src/agent_platform/core/config/
done

# Copy domain/** -> src/agent_platform/domain/**
for f in packages/core/src/agent_platform_core/domain/*.py; do
  cp "$f" src/agent_platform/domain/
done

# Copy config/** -> src/agent_platform/config/**
for f in packages/core/src/agent_platform_core/config/*.py; do
  cp "$f" src/agent_platform/config/
done

echo "Real source files copied."

echo "=== Step 3-5: Counting references before replacement ==="
before_count=$(grep -r 'agent_platform_core' src/agent_platform/ tests/ --include='*.py' -l 2>/dev/null | wc -l)
echo "Files with agent_platform_core references: $before_count"

import_count=$(grep -r -c 'from agent_platform_core\.\|import agent_platform_core\.' src/agent_platform/ tests/ --include='*.py' 2>/dev/null | awk -F: '{s+=$NF}END{print s}')
echo "Import lines to replace: $import_count"

# Replace in all .py files under src/agent_platform/ and tests/
find src/agent_platform/ tests/ -name '*.py' -not -path '*__pycache__*' -exec \
  sed -i 's/from agent_platform_core\./from agent_platform./g' {} +
find src/agent_platform/ tests/ -name '*.py' -not -path '*__pycache__*' -exec \
  sed -i 's/import agent_platform_core\./import agent_platform./g' {} +
# Catch remaining references in docstrings/comments (full namespace without dot)
find src/agent_platform/ tests/ -name '*.py' -not -path '*__pycache__*' -exec \
  sed -i 's/agent_platform_core/agent_platform/g' {} +

echo "=== Step 3-5: Verifying replacements ==="
after_count=$(grep -r 'agent_platform_core' src/agent_platform/ tests/ --include='*.py' -l 2>/dev/null | wc -l)
echo "Files still with agent_platform_core references: $after_count"

echo "=== COMPLETE ==="
