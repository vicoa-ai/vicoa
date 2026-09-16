#!/bin/bash
# One-shot backend dev-environment setup for a fresh checkout or worktree.
#
# Needs nothing but a Python interpreter (3.10+, per pyproject; 3.12 preferred
# to match CI and the Dockerfile) — no uv, pyenv, or other tooling. Creates a
# stdlib .venv, installs runtime + dev deps with pip via `make dev-install`,
# and installs the local package editable. Idempotent — safe to re-run; it
# reuses an existing .venv, including one created by `uv venv` (which ships
# without pip; ensurepip bootstraps one).
#
# The automatic worktree setup (.vicoa/config.json) calls this script, so the
# venv logic lives in exactly one place.
#
# Usage:  ./scripts/dev-setup.sh                          (from backend/)
#         VICOA_PYTHON=/path/to/python3.12 ./scripts/dev-setup.sh

set -eu

MIN_PYTHON="3.10"   # pyproject requires-python

# Resolve backend/ so the script works no matter where it is called from.
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

echo "=== backend dev-setup ($BACKEND_DIR) ==="

# 1) pick an interpreter: explicit override, then versioned names (preferred
#    first), then whatever `python3` is on PATH — which is often conda or a
#    system Python, hence the version check below.
find_python() {
    if [ -n "${VICOA_PYTHON:-}" ]; then
        echo "$VICOA_PYTHON"
        return
    fi
    local candidate
    for candidate in python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" > /dev/null 2>&1; then
            command -v "$candidate"
            return
        fi
    done
}

python_ok() {
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(map(int, '$MIN_PYTHON'.split('.'))) else 1)" 2> /dev/null
}

# 2) create the venv (or reuse it), and make sure it can run pip.
if [ ! -d .venv ]; then
    PY="$(find_python)"
    if [ -z "$PY" ]; then
        echo "Error: no python3 found on PATH. Install Python $MIN_PYTHON+ or set VICOA_PYTHON=/path/to/python."
        exit 1
    fi
    if ! python_ok "$PY"; then
        echo "Error: $PY is $("$PY" --version 2>&1); need Python $MIN_PYTHON+ (set VICOA_PYTHON to pick another)."
        exit 1
    fi
    echo "--- creating .venv with $PY ($("$PY" --version 2>&1)) ---"
    "$PY" -m venv .venv
else
    echo "--- reusing existing .venv ($(./.venv/bin/python --version 2>&1)) ---"
    if ! python_ok ./.venv/bin/python; then
        echo "Error: .venv is on $(./.venv/bin/python --version 2>&1), need $MIN_PYTHON+. Delete backend/.venv and re-run."
        exit 1
    fi
fi

# A venv made by `uv venv` has no pip, and a bare `pip` would then fall
# through to whatever global pip is on PATH and install into the wrong place.
# Stdlib ensurepip bootstraps one into the venv.
if ! ./.venv/bin/python -m pip --version > /dev/null 2>&1; then
    echo "--- .venv has no pip; bootstrapping with ensurepip ---"
    ./.venv/bin/python -m ensurepip --upgrade
fi
./.venv/bin/python -m pip install -q --upgrade pip

# 3) install into the venv. Activation persists for the rest of THIS script
#    (PATH points pip/python at .venv), but not into your interactive shell.
#    Guard the sourcing against unset-var quirks in older activate scripts.
set +u
# shellcheck disable=SC1091
source .venv/bin/activate
set -u

# `make dev-install` runs a bare `pip`; refuse to continue unless that is the
# venv's pip.
case "$(command -v pip)" in
    "$BACKEND_DIR"/.venv/*) ;;
    *)
        echo "Error: 'pip' resolves to $(command -v pip), not $BACKEND_DIR/.venv/bin/pip."
        exit 1
        ;;
esac

echo "--- make dev-install ---"
make dev-install

echo "--- pip install -e . (editable local package) ---"
pip install -e .

echo "=== done ==="
echo "Activate it in your shell:  source backend/.venv/bin/activate"
