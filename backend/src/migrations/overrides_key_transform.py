"""
Pure, DB-free overlay-key transform for the Phase 2 ``overrides -> fixed_overrides`` migration.

Phase 2 (Delete the Redundant Surface), Deliverable 2, R6.1-R6.5 / R8.2.

This module holds ONLY the pure row transform (``rename_overrides_key``) and its
companion predicate (``overlay_needs_rewrite``). It imports NO database layer
(``database`` / ``mysql.connector``) and NO service layer, so it can be imported from
any plane — including the SAM/DynamoDB-plane invariance test — without dragging in
``mysql-connector-python``.

The DB-bound migration driver lives in ``migrate_overrides_to_fixed_overrides.py`` and
re-exports these functions, so existing callers and tests that import them from the
migration module keep working.
"""

from __future__ import annotations

from typing import Any

#: The legacy top-level key being retired and the canonical key it folds into.
_LEGACY_KEY = "overrides"
_CANONICAL_KEY = "fixed_overrides"


def overlay_needs_rewrite(overlay: Any) -> bool:
    """True iff ``overlay`` is a dict carrying a top-level ``overrides`` key whose VALUE is a dict.

    Pure predicate (no DB) so callers and tests can decide whether a row would change
    without mutating it. The trigger is a top-level ``overrides`` key whose VALUE is a
    dict — that is the only shape that carries migratable entries. A non-dict overlay,
    an overlay without a top-level ``overrides`` key, or one whose ``overrides`` value
    is ``None`` / any non-dict, never needs a rewrite (so the migration is a no-op on
    it — idempotence, and it never touches a mis-fed non-overlay record's bytes).
    """
    return isinstance(overlay, dict) and isinstance(overlay.get(_LEGACY_KEY), dict)


def rename_overrides_key(overlay: Any) -> Any:
    """Return a NEW overlay with the legacy ``overrides`` key folded into ``fixed_overrides``.

    Pure, DB-free, and importable so the paired test (task 5.2) can exercise the merge
    invariant, the collision rule, and idempotence without any database.

    Rules:
      - If ``overlay`` is not a dict, or carries no top-level ``overrides`` key whose
        VALUE is a dict (e.g. ``overrides`` is ``None`` or any non-dict), it is returned
        UNCHANGED (same object) — the migration does nothing to it. This guarantees a
        mis-fed non-overlay record (e.g. a member record carrying ``overrides: None``)
        comes back BYTE-FOR-BYTE UNCHANGED.
      - Otherwise a shallow copy is made, the top-level ``overrides`` key is removed, and
        its entries are merged into ``fixed_overrides``. On a per-key collision the
        PRE-EXISTING ``fixed_overrides`` entry WINS (the canonical authored key). Keys
        only in ``overrides`` are moved in. Override VALUES are copied verbatim.
      - Only the KEY NAME is rewritten — every OTHER top-level overlay key (``fields``,
        labels, etc.) is left exactly as-is.

    Idempotent by construction: the result never carries a top-level ``overrides`` key,
    so ``rename_overrides_key(rename_overrides_key(x)) == rename_overrides_key(x)``.
    """
    if not isinstance(overlay, dict) or not isinstance(overlay.get(_LEGACY_KEY), dict):
        return overlay

    # Shallow copy of the overlay; drop the legacy key, keep every other key as-is.
    new_overlay = dict(overlay)
    legacy_overrides = new_overlay.pop(_LEGACY_KEY)
    existing_fixed = new_overlay.get(_CANONICAL_KEY)

    # Build the merged map: legacy entries first, then the canonical fixed_overrides
    # entries OVERWRITE them, so on a per-key collision the authored fixed_overrides
    # entry WINS (R6.2). Keys present only under the legacy map are moved in. Values
    # are copied verbatim (never altered). Non-dict operands are tolerated defensively
    # (a non-dict side simply contributes nothing to the merge).
    merged: dict[str, Any] = {}
    if isinstance(legacy_overrides, dict):
        merged.update(legacy_overrides)
    if isinstance(existing_fixed, dict):
        merged.update(existing_fixed)

    new_overlay[_CANONICAL_KEY] = merged
    return new_overlay
