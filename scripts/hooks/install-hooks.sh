#!/bin/sh
# ---------------------------------------------------------------------------
# Installs the committed git hooks into this working copy's .git/hooks/.
#
# Usage (from the repo root):
#   sh scripts/hooks/install-hooks.sh
#
# It symlinks each committed hook under scripts/hooks/ into .git/hooks/ (falling
# back to a copy if symlinks are unavailable) and marks it executable:
#   - pre-commit : ggshield secret scan + ruff check / ruff format --check
#   - pre-push   : clean-checkout guard — SAM collect smoke test PLUS
#                  `ruff check src/` and `ruff format --check src/` over the
#                  whole backend/src/ tree (mirrors the CI lint job), PLUS a
#                  changed-path pytest subset (via scoped_runner) for the
#                  backend files being pushed. Catches runtime test / lint /
#                  format regressions, and an untracked-but-required module,
#                  before they reach CI. The clean-checkout stash covers tracked
#                  changes + untracked files but NOT ignored files (so an
#                  unreadable ignored data dir like a running Docker mysql_data/
#                  can't make the guard fail-open); a stash failure now ABORTS
#                  the push rather than silently skipping the gates.
#                  Opt out with SKIP_PREPUSH=1 (or legacy SKIP_PREPUSH_COLLECT=1).
# Replacing any old .git/hooks/<name> loses nothing.
# ---------------------------------------------------------------------------
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$GIT_HOOKS_DIR" ]; then
    echo "install-hooks: ERROR $GIT_HOOKS_DIR not found (is this a git repo?)" >&2
    exit 1
fi

install_hook() {
    name="$1"
    src="$REPO_ROOT/scripts/hooks/$name"
    dest="$GIT_HOOKS_DIR/$name"

    if [ ! -f "$src" ]; then
        echo "install-hooks: ERROR source hook not found at $src" >&2
        exit 1
    fi

    # Prefer a symlink so the installed hook tracks the committed source; fall
    # back to a copy if the platform/filesystem does not support symlinks.
    if ln -sf "$src" "$dest" 2>/dev/null; then
        echo "install-hooks: symlinked $dest -> $src"
    else
        cp "$src" "$dest"
        echo "install-hooks: copied $src -> $dest"
    fi

    chmod +x "$src" "$dest" 2>/dev/null || true
}

install_hook pre-commit
install_hook pre-push

echo "install-hooks: pre-commit + pre-push hooks installed."
