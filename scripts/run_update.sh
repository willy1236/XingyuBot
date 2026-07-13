#!/usr/bin/env bash
# 走 git 同步流程：檢查分支、確認無本機變更，然後 fetch + fast-forward pull
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[Update Module] PWD: $(pwd)"
echo "[Update Module] git dir: $(git rev-parse --git-dir 2>&1)"
echo "[Update Module] branch raw: $(git rev-parse --abbrev-ref HEAD 2>&1)"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"

if [[ -z "$CURRENT_BRANCH" ]]; then
    echo "[Update Module] Unable to determine current branch"
    exit 1
fi

if [[ "$CURRENT_BRANCH" == "HEAD" ]]; then
    echo "[Update Module] Detached HEAD state, abort update"
    exit 1
fi

if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "[Update Module] Working tree has local changes, abort update"
    exit 1
fi

echo "[Update Module] Current branch: $CURRENT_BRANCH"

if ! git fetch origin; then
    exit 1
fi

if ! git pull --ff-only origin "$CURRENT_BRANCH"; then
    exit 1
fi

echo "[Update Module] Update successful"
