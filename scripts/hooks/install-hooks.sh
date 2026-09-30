#!/bin/sh
# ---------------------------------------------------------------------------
# Installs the committed git hooks into this working copy's .git/hooks/.
#
# Usage (from the repo root):
#   sh scripts/hooks/install-hooks.sh
#
# It symlinks scripts/hooks/pre-commit -> .git/hooks/pre-commit (falling back
# to a copy if symlinks are unavailable) and marks it executable. The committed
# hook itself runs the ggshield secret scan plus ruff check / ruff format
# --check, so replacing the old .git/hooks/pre-commit loses nothing.
# ---------------------------------------------------------------------------
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO_ROOT/scripts/hooks/pre-commit"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"
DEST="$GIT_HOOKS_DIR/pre-commit"

if [ ! -f "$SRC" ]; then
    echo "install-hooks: ERROR source hook not found at $SRC" >&2
    exit 1
fi

if [ ! -d "$GIT_HOOKS_DIR" ]; then
    echo "install-hooks: ERROR $GIT_HOOKS_DIR not found (is this a git repo?)" >&2
    exit 1
fi

# Prefer a symlink so the installed hook tracks the committed source; fall back
# to a copy if the platform/filesystem does not support symlinks.
if ln -sf "$SRC" "$DEST" 2>/dev/null; then
    echo "install-hooks: symlinked $DEST -> $SRC"
else
    cp "$SRC" "$DEST"
    echo "install-hooks: copied $SRC -> $DEST"
fi

chmod +x "$SRC" "$DEST" 2>/dev/null || true

echo "install-hooks: pre-commit hook installed."
