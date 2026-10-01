"""paths.py — robust repo-root + sys.path resolution for onboarding runners (R4.1/R4.2).

Replaces the fragile ``os.path.dirname(os.path.dirname(os.path.dirname(__file__)))`` blocks that
the onboarding runners previously carried. Those break the moment a script changes depth; this
module instead walks UP from a starting path until it finds a repo MARKER, so a runner can live
at any depth under the repo and still resolve the root.

Public API
----------
- :func:`repo_root` — the repository root (cached), found by marker walk.
- :func:`ensure_backend_src_on_path` — idempotently put repo root + ``backend/src`` on
  ``sys.path`` (so ``import sam.members...`` and its ``services.*`` deps resolve).
- :func:`import_by_path` — import a module directly from a file path (for modules that live
  outside any importable package, e.g. a dashed tenant dir like ``members/h-dcn/``).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType

#: Files/dirs that, taken TOGETHER, uniquely identify this repo's root. We require a
#: combination rather than a single generic name so the walk never stops at an unrelated
#: ancestor that merely happens to contain, say, a ``backend`` directory.
_MARKERS: tuple[tuple[str, ...], ...] = (
    (".git",),              # the obvious one for a working clone
    ("backend", "sam", ".kiro"),  # belt-and-suspenders for worktrees / exported trees
)

_cached_root: str | None = None


def _is_repo_root(path: str) -> bool:
    for marker in _MARKERS:
        if all(os.path.exists(os.path.join(path, name)) for name in marker):
            return True
    return False


def repo_root(start: str | None = None) -> str:
    """Return the repository root by walking UP from ``start`` (default: this file).

    Cached after the first successful resolution. Raises ``RuntimeError`` with a clear message
    if no marker is found all the way to the filesystem root (so a misplaced checkout fails
    loudly instead of silently resolving to ``/``).
    """
    global _cached_root
    if start is None:
        if _cached_root is not None:
            return _cached_root
        start = os.path.dirname(os.path.abspath(__file__))

    current = os.path.abspath(start)
    while True:
        if _is_repo_root(current):
            if start == os.path.dirname(os.path.abspath(__file__)):
                _cached_root = current
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root without a marker
            raise RuntimeError(
                "Could not locate the repository root walking up from "
                f"{os.path.abspath(start)!r}: no marker "
                f"({' or '.join('+'.join(m) for m in _MARKERS)}) found. "
                "Is this file inside the repo?"
            )
        current = parent


def ensure_backend_src_on_path(start: str | None = None) -> str:
    """Idempotently put repo root + ``backend/src`` on ``sys.path``; return the repo root.

    Mirrors the historical per-script block (repo root first so ``sam.*`` imports, then
    ``backend/src`` so its ``services.*`` / ``auth.*`` dependencies import) but computed from
    the marker walk, not a fixed number of ``dirname`` hops.
    """
    root = repo_root(start)
    backend_src = os.path.join(root, "backend", "src")
    for entry in (root, backend_src):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return root


def import_by_path(module_name: str, file_path: str) -> ModuleType:
    """Import and return a module directly from ``file_path`` under the name ``module_name``.

    Used for modules that are NOT part of an importable package — e.g. the tenant config
    loaders under the dashed ``members/h-dcn/`` directory. Replaces ad-hoc
    ``importlib.util.spec_from_file_location`` blocks copied into individual runners (R4.2).

    Raises ``FileNotFoundError`` with a clear message if the file is absent.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Cannot import {module_name!r}: no file at {file_path!r}."
        )
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Could not build an import spec for {file_path!r}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
