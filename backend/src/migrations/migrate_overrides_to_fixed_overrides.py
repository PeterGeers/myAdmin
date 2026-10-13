"""
Migration: members.field_overlay legacy ``overrides`` key -> ``fixed_overrides``

Phase 2 (Delete the Redundant Surface), Deliverable 2, R6.1-R6.5 / R8.2.

Rewrites every stored ``members.field_overlay`` config row whose overlay JSON carries
a legacy TOP-LEVEL ``overrides`` key so the data lives under the canonical
``fixed_overrides`` key instead. The legacy dual-accept read branches (Flask builder +
SAM reader) are deleted in a LATER task (5.3), gated on this migration having run.

What it does (and does NOT do):
  - Rewrites the stored JSON KEY NAME only: a top-level ``overrides`` map is merged into
    ``fixed_overrides``. On a per-key collision the EXISTING ``fixed_overrides`` entry
    WINS (it is the authored/validated key). Keys present only under ``overrides`` move in.
  - Copies the override VALUES verbatim — they are the owner's data (`31` Data Ownership).
  - Touches NO member records and NO other overlay keys (R6.3, R8.1/R8.3).
  - Is idempotent: after the rename no row carries a top-level ``overrides`` key, so a
    re-run is a no-op (R6.4).
  - ``administration``-scoped: operates ONLY on ``scope='tenant'`` ``members.field_overlay``
    parameter rows, keyed by the ``scope_id`` (= ``administration``). Parameterized queries.
  - ``--dry-run`` is the DEFAULT: a dry run makes NO DB change; pass ``--apply`` to write.

Applied MANUALLY via the migration-runner mechanism (NOT auto-applied on startup, `31`).
The row transform is a per-row JSON merge with a collision rule, which a static-SQL
``.json`` migration cannot express, so it is a ``.py`` migration modeled on
``migrate_tenant_config_to_parameters.py`` (same ``DatabaseManager`` + ``ParameterService``
usage, same ``--dry-run`` default, same manual-run contract).

Usage:
  cd backend && source .venv/bin/activate
  # dry run (default — no DB change):
  python -m src.migrations.migrate_overrides_to_fixed_overrides
  # apply:
  python -m src.migrations.migrate_overrides_to_fixed_overrides --apply
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Add src to path (match migrate_tenant_config_to_parameters.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import DatabaseManager
from services.parameter_service import ParameterService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

#: The members-namespace parameter whose stored JSON carries the overlay.
_MEMBERS_NAMESPACE = "members"
_FIELD_OVERLAY_KEY = "field_overlay"

#: The legacy top-level key being retired and the canonical key it folds into.
_LEGACY_KEY = "overrides"
_CANONICAL_KEY = "fixed_overrides"


def overlay_needs_rewrite(overlay: Any) -> bool:
    """True iff ``overlay`` is a dict carrying a top-level legacy ``overrides`` key.

    Pure predicate (no DB) so callers and tests can decide whether a row would change
    without mutating it. A non-dict overlay, or one without a top-level ``overrides``
    key, never needs a rewrite (so the migration is a no-op on it — idempotence).
    """
    return isinstance(overlay, dict) and _LEGACY_KEY in overlay


def rename_overrides_key(overlay: Any) -> Any:
    """Return a NEW overlay with the legacy ``overrides`` key folded into ``fixed_overrides``.

    Pure, DB-free, and importable so the paired test (task 5.2) can exercise the merge
    invariant, the collision rule, and idempotence without any database.

    Rules:
      - If ``overlay`` is not a dict, or carries no top-level ``overrides`` key, it is
        returned UNCHANGED (same object) — the migration does nothing to it.
      - Otherwise a shallow copy is made, the top-level ``overrides`` key is removed, and
        its entries are merged into ``fixed_overrides``. On a per-key collision the
        PRE-EXISTING ``fixed_overrides`` entry WINS (the canonical authored key). Keys
        only in ``overrides`` are moved in. Override VALUES are copied verbatim.
      - Only the KEY NAME is rewritten — every OTHER top-level overlay key (``fields``,
        labels, etc.) is left exactly as-is.

    Idempotent by construction: the result never carries a top-level ``overrides`` key,
    so ``rename_overrides_key(rename_overrides_key(x)) == rename_overrides_key(x)``.
    """
    if not isinstance(overlay, dict) or _LEGACY_KEY not in overlay:
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


def migrate(dry_run: bool = True) -> dict:
    """Rewrite every tenant ``members.field_overlay`` row carrying a legacy ``overrides`` key.

    ``administration``-scoped: reads the ``parameters`` table for ``scope='tenant'``
    ``members.field_overlay`` rows (``scope_id`` is the ``administration``), parameterized.
    Dry run (DEFAULT) logs the intended change and makes NO DB write. Returns a summary
    dict ``{scanned, rewritten, skipped}`` for callers/tests.
    """
    db = DatabaseManager()
    param_service = ParameterService(db)

    # administration-scoped sweep: only tenant-scope members.field_overlay rows.
    rows = db.execute_query(
        """
        SELECT scope_id, value, value_type, is_secret
        FROM parameters
        WHERE scope = %s AND namespace = %s AND `key` = %s
        ORDER BY scope_id
        """,
        ("tenant", _MEMBERS_NAMESPACE, _FIELD_OVERLAY_KEY),
        fetch=True,
    )

    summary = {"scanned": 0, "rewritten": 0, "skipped": 0}

    if not rows:
        logger.info("No tenant members.field_overlay rows found. Nothing to migrate.")
        return summary

    logger.info("Scanning %d tenant members.field_overlay row(s).", len(rows))

    for row in rows:
        summary["scanned"] += 1
        administration = row["scope_id"]
        raw_value = row["value"]

        # Secret overlays are not expected (field_overlay is plain config), but if one is
        # flagged secret we cannot safely re-encrypt here — skip and surface it.
        if row.get("is_secret"):
            logger.warning(
                "  SKIP %s: field_overlay row flagged is_secret; not rewriting.",
                administration,
            )
            summary["skipped"] += 1
            continue

        try:
            overlay = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "  SKIP %s: field_overlay value is not valid JSON; leaving untouched.",
                administration,
            )
            summary["skipped"] += 1
            continue

        if not overlay_needs_rewrite(overlay):
            summary["skipped"] += 1
            continue

        new_overlay = rename_overrides_key(overlay)

        if dry_run:
            logger.info(
                "  [DRY RUN] %s: fold top-level 'overrides' into 'fixed_overrides' "
                "(fixed_overrides wins on collision).",
                administration,
            )
            summary["rewritten"] += 1
            continue

        try:
            # Write back via ParameterService (handles JSON encoding + cache invalidation).
            # value_type stays 'json' (the overlay is an object).
            param_service.set_param(
                scope="tenant",
                scope_id=administration,
                namespace=_MEMBERS_NAMESPACE,
                key=_FIELD_OVERLAY_KEY,
                value=new_overlay,
                value_type="json",
                is_secret=False,
                created_by="migration_phase2_overrides_rename",
            )
            summary["rewritten"] += 1
            logger.info("  OK %s: overrides -> fixed_overrides", administration)
        except Exception as e:
            logger.error("  FAIL %s: %s", administration, e)
            summary["skipped"] += 1

    mode = "DRY RUN" if dry_run else "APPLIED"
    logger.info(
        "\nMigration complete (%s): %d scanned, %d rewritten, %d skipped.",
        mode,
        summary["scanned"],
        summary["rewritten"],
        summary["skipped"],
    )
    return summary


if __name__ == "__main__":
    # Dry run is the DEFAULT (R6.5). Require an explicit --apply to write.
    apply = "--apply" in sys.argv
    dry_run = not apply
    if dry_run:
        logger.info("=== DRY RUN MODE (no DB change) — pass --apply to write ===")
    migrate(dry_run=dry_run)
