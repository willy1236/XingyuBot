#!/usr/bin/env bash
# 對應 scripts/run_main.bat：先跑 run_update.sh 同步 git，再 uv sync，最後啟動主程式
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# "$SCRIPT_DIR/run_update.sh"
# if [[ $? -ne 0 ]]; then
#     exit 1
# fi

cd "$SCRIPT_DIR/.."

uv sync
if [[ $? -ne 0 ]]; then
    exit 1
fi

export APP_ENV=production
export PYTHONWARNINGS=ignore::DeprecationWarning
# 直接 exec venv 的 python，不經 uv run：systemd 停服務時會對 cgroup 內每個 process 送 SIGTERM，
# uv run 又會把收到的 SIGTERM 轉送給子程序，python 收到兩次會在 py-cord 清理途中再次 loop.stop()，
# 拋出 RuntimeError: Event loop stopped before Future completed.
exec "${UV_PROJECT_ENVIRONMENT:-.venv}/bin/python" -W ignore -m main
