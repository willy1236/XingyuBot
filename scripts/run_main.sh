#!/usr/bin/env bash
# 對應 scripts/run_main.bat：先跑 run_update.sh 同步 git，再 uv sync，最後啟動主程式
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./run_update.sh
if [[ $? -ne 0 ]]; then
    exit 1
fi

uv sync
if [[ $? -ne 0 ]]; then
    exit 1
fi

cd "$SCRIPT_DIR/.."
export APP_ENV=production
export PYTHONWARNINGS=ignore::DeprecationWarning
exec uv run python -W ignore -m main
