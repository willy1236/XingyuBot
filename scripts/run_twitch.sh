#!/usr/bin/env bash
# Twitch bot 的正式機啟動腳本，對應 scripts/run_main.sh：先 uv sync，再啟動 twitch_main
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

uv sync
if [[ $? -ne 0 ]]; then
    exit 1
fi

export APP_ENV=production
export PYTHONWARNINGS=ignore::DeprecationWarning
# 理由同 run_main.sh：不經 uv run，避免 SIGTERM 被轉送兩次
exec "${UV_PROJECT_ENVIRONMENT:-.venv}/bin/python" -W ignore -m twitch_main
