#!/usr/bin/env bash
# Continuously sync the project to the Pi whenever files change.
#
# Set the target with env vars (no hardcoded host/user/path):
#   PI_HOST=you@your-pi.local PI_PATH=briefer/ ./scripts/sync-to-pi.sh
#
# PI_HOST is required; PI_PATH defaults to ~/briefer/ on the Pi (a relative path
# is created under the login user's home, no root needed).
# Requires: fswatch (brew install fswatch)

set -euo pipefail

HOST="${PI_HOST:?set PI_HOST=user@host (e.g. you@your-pi.local)}"
REMOTE="${PI_PATH:-briefer/}"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)/"

do_sync() {
  rsync -av --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='config.toml' \
    "$LOCAL" "$HOST:$REMOTE"
}

echo "==> ensuring $HOST:$REMOTE exists"
ssh "$HOST" "mkdir -p '$REMOTE'"

echo "==> initial sync to $HOST:$REMOTE"
do_sync

echo "==> watching for changes (Ctrl-C to stop)..."
fswatch -o \
  --exclude='\.venv' \
  --exclude='__pycache__' \
  --exclude='\.pytest_cache' \
  --exclude='\.git' \
  --exclude='\.pyc$' \
  --exclude='config.toml' \
  "$LOCAL" | while read -r; do
    echo "==> change detected, syncing..."
    do_sync
  done
