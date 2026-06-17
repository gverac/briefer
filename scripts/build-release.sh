#!/usr/bin/env bash
# Build a release tarball to hand to a friend for uploading via the console
# (Software page). The archive contains the app source only — no .venv, .git,
# config.toml, or caches — and is rebuilt fresh on the device.
#
# Usage:
#   ./scripts/build-release.sh [output-dir]          # release: from committed HEAD
#   ./scripts/build-release.sh --dev [output-dir]    # dev: bundle the working tree
#
# A normal build archives the committed tree (git HEAD) and REFUSES to run with
# uncommitted changes — otherwise the version string (read from the working-tree
# file) and the shipped code can disagree. Use --dev to bundle your working tree
# as-is (committed or not); its version is tagged `+dev` so it's never mistaken
# for a real release.
#
# Output: <output-dir>/briefer-<version>.tgz   (default output-dir: ./dist)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DEV=0
OUT_DIR=""
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "error: unknown option: $arg" >&2; exit 2 ;;
    *) OUT_DIR="$arg" ;;
  esac
done
OUT_DIR="${OUT_DIR:-$ROOT/dist}"

# Base version comes from the package source.
BASE_VERSION="$(grep -oE '"[^"]+"' "$ROOT/daily_brief/__init__.py" | tr -d '"' | tail -1)"

HAS_GIT=0
SHA=""
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  HAS_GIT=1
  SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
fi

mkdir -p "$OUT_DIR"

# Bundle the on-disk working tree into $1, prefixed with briefer/. Uses an rsync
# staging dir so it's portable across GNU and BSD (macOS) tar, which disagree on
# path-rewriting flags.
bundle_worktree() {
  local tarball="$1" stage
  stage="$(mktemp -d)"
  trap 'rm -rf "$stage"' RETURN
  rsync -a \
    --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='*.pyc' --exclude='config.toml' \
    --exclude='dist' \
    "$ROOT/" "$stage/briefer/"
  tar -czf "$tarball" -C "$stage" briefer
}

if [ "$DEV" -eq 1 ]; then
  # Dev build: bundle the working tree exactly as it is on disk.
  VERSION="${BASE_VERSION}+dev${SHA:+-$SHA}"
  TARBALL="$OUT_DIR/briefer-${VERSION}.tgz"
  bundle_worktree "$TARBALL"
  echo "built (dev) $TARBALL"
  echo "WARNING: dev build — bundles uncommitted code; not for handing out as a release."
  exit 0
fi

# Release build: archive the committed tree, and refuse if it's dirty so the
# version (from the working-tree file) always matches the shipped code.
if [ "$HAS_GIT" -eq 1 ]; then
  if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
    echo "error: uncommitted changes in the working tree." >&2
    echo "       A release is built from the committed tree (git HEAD), so the" >&2
    echo "       version and the shipped code would disagree. Commit your changes" >&2
    echo "       first, or run with --dev to bundle the working tree as-is." >&2
    git -C "$ROOT" status --short >&2
    exit 1
  fi
  VERSION="${BASE_VERSION}${SHA:+ +$SHA}"
  VERSION="${VERSION// /}"
  TARBALL="$OUT_DIR/briefer-${VERSION}.tgz"
  git -C "$ROOT" archive --format=tar.gz --prefix="briefer/" -o "$TARBALL" HEAD
else
  # No git repo: nothing to be "committed" against, so bundle the tree directly.
  VERSION="${BASE_VERSION}"
  TARBALL="$OUT_DIR/briefer-${VERSION}.tgz"
  bundle_worktree "$TARBALL"
fi

echo "built $TARBALL"
