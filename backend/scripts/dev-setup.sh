#!/bin/bash
# One-shot backend dev-environment setup for a fresh checkout or worktree.
#
# OPTIONAL and opt-in: run this only in a worktree where you actually work on
# the backend. It is intentionally NOT part of the automatic worktree setup
# (.vicoa/config.json) because installing the Python deps is slow and most
# worktrees never touch the backend.
#
# Creates a .venv on the project's target Python (3.12), installs runtime +
# dev deps, and installs the local package editable. Idempotent — safe to
# re-run; it reuses an existing .venv.
#
# Usage:  ./scripts/dev-setup.sh    (from the backend/ directory)

set -e

PYTHON_VERSION="3.12"

# Resolve backend/ so the script works no matter where it is called from.
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

echo "=== backend dev-setup ($BACKEND_DIR) ==="

if ! command -v uv > /dev/null 2>&1; then
    echo "Error: 'uv' is not installed."
    echo "Install it (https://docs.astral.sh/uv/) or create the venv manually:"
    echo "  python3.${PYTHON_VERSION#3.} -m venv .venv && source .venv/bin/activate && make dev-install && pip install -e ."
    exit 1
fi

# 1) venv on the project's target Python (uv auto-downloads 3.12 if missing).
if [ ! -d .venv ]; then
    echo "--- creating .venv on Python $PYTHON_VERSION ---"
    uv venv --python "$PYTHON_VERSION" .venv
else
    echo "--- reusing existing .venv ---"
fi

# 2) install into the venv. Activation persists for the rest of THIS script
#    (PATH points pip/python at .venv), but not into your interactive shell.
#    Guard the sourcing against 'set -e'/unset-var quirks in older activate
#    scripts.
set +u
# shellcheck disable=SC1091
source .venv/bin/activate
set -u

echo "--- make dev-install ---"
make dev-install

echo "--- pip install -e . (editable local package) ---"
pip install -e .

echo "=== done ==="
echo "Activate it in your shell:  source backend/.venv/bin/activate"
