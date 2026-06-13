#!/usr/bin/env bash
# Continuously sync the project to the Pi whenever files change.
# Usage:  ./scripts/sync-to-pi.sh
# Requires: fswatch (brew install fswatch)

set -euo pipefail

HOST="gvera@beech"
REMOTE="/home/gvera/brief/"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)/"

do_sync() {
  rsync -av --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.git' \
    --exclude='*.pyc' \
    "$LOCAL" "$HOST:$REMOTE"
}

echo "==> initial sync to $HOST:$REMOTE"
do_sync

echo "==> watching for changes (Ctrl-C to stop)..."
fswatch -o \
  --exclude='\.venv' \
  --exclude='__pycache__' \
  --exclude='\.pytest_cache' \
  --exclude='\.git' \
  --exclude='\.pyc$' \
  "$LOCAL" | while read -r; do
    echo "==> change detected, syncing..."
    do_sync
  done
