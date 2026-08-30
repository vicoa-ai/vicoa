#!/bin/bash
# Script to run linting and type checking

set -e

echo "Running ruff check..."
ruff check . --exclude src/integrations/cli_wrappers/codex

echo -e "\nRunning ruff format check..."
ruff format --check . --exclude src/integrations/cli_wrappers/codex

echo -e "\nRunning pyright..."
pyright

echo -e "\nRunning WebSocket migration freeze check..."
python "$(dirname "$0")/check_websocket_freeze.py"

echo -e "\nAll checks passed!"
