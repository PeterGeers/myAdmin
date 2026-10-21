"""
Migration: retire the Members ``view_contexts`` parameter rows.

Phase 2 (Retire ``view_contexts``), step (d) — R2.1.

Deletes every stored ``members.view_contexts`` tenant parameter row from the
``parameters`` table. ``view_contexts`` is a RETIRED Members config surface: the only
column-layout value that survived (``page_size``) was re-homed to the ``default_page_size``
scalar on ``config#fields`` in an earlier step; no live code READS ``view_contexts`` any
more. This migration removes the residual stored rows. (The matching ``config#views``
PROJECTION residue removal is task 5.2 — a separate step; this migration is the MySQL
``parameters``-row deletion only.)

What it does (and does NOT do):
  - Deletes rows WHERE ``scope='tenant'`` AND ``namespace='members'`` AND ``key='view_contexts'``
    from the ``parameters`` table (parameterized ``%s`` placeholders — no interpolation).
  - ``administration``-scoped: it operates across tenants via the ``scope='tenant'`` filter,
    never a hardcoded tenant name — the tenant (``scope_id``) values flow from the data, not
    from literals (`31` Data Ownership).
  - Touches NO other namespace, key, or scope. No member records, no surviving config keys
    (``default_page_size`` / Session Columns are untouched — R2.5).
  - Is idempotent: once the targeted rows are gone a re-run matches 0 rows and deletes 0,
    a safe no-op (R2.1).
  - ``--dry-run`` is the DEFAULT: a dry run COUNTS the matching rows and makes NO DB change;
    pass ``--apply`` to actually DELETE.

Applied MANUALLY (NOT auto-applied on startup, `31`). The operation is a straight targeted
DELETE, but it is modeled on ``migrate_overrides_to_fixed_overrides.py`` (same
``DatabaseManager`` usage via the abstraction layer, same ``--dry-run`` default, same
manual-run contract, same ``migrate()`` entrypoint returning a summary dict).

Usage:
  cd backend && source .venv/bin/activate
  # dry run (default — no DB change):
  python -m src.migrations.retire_members_view_contexts
  # apply:
  python -m src.migrations.retire_members_view_contexts --apply
"""

from __future__ import annotations

import logging
import os
import sys

# Add src to path (match migrate_overrides_to_fixed_overrides.py) so `from database import
# DatabaseManager` resolves whether this module is loaded as
# `migrations.retire_members_view_contexts` (src on path) or with `src/migrations` directly
# on sys.path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

#: The retired members-namespace parameter whose rows this migration deletes.
_SCOPE = "tenant"
_MEMBERS_NAMESPACE = "members"
_VIEW_CONTEXTS_KEY = "view_contexts"


def migrate(db: DatabaseManager | None = None, dry_run: bool = True) -> dict:
    """Delete every tenant ``members.view_contexts`` row from ``parameters``.

    ``administration``-scoped: targets ``scope='tenant'`` ``members.view_contexts`` rows
    (``scope_id`` is the ``administration``), parameterized — no tenant name is hardcoded.
    Dry run (DEFAULT) COUNTS the matching rows and makes NO DB write. ``--apply`` performs
    the DELETE. Idempotent: a re-run after a successful apply matches 0 rows.

    ``db`` is injectable so the migration is testable with a mock handle (task 5.3);
    defaults to a real ``DatabaseManager`` for manual runs. Returns a summary dict
    ``{scanned, deleted}``.
    """
    if db is None:
        db = DatabaseManager()

    # administration-scoped count: how many tenant members.view_contexts rows exist.
    count_rows = db.execute_query(
        """
        SELECT COUNT(*) AS n
        FROM parameters
        WHERE scope = %s AND namespace = %s AND `key` = %s
        """,
        (_SCOPE, _MEMBERS_NAMESPACE, _VIEW_CONTEXTS_KEY),
        fetch=True,
    )

    # execute_query returns a list of dict rows; be tolerant of an empty result.
    scanned = 0
    if count_rows:
        first = count_rows[0]
        scanned = int(first["n"] if isinstance(first, dict) else first[0])

    summary = {"scanned": scanned, "deleted": 0}

    if scanned == 0:
        logger.info(
            "No tenant members.view_contexts rows found. Nothing to delete (no-op)."
        )
        return summary

    logger.info("Found %d tenant members.view_contexts row(s).", scanned)

    if dry_run:
        logger.info(
            "  [DRY RUN] would DELETE %d tenant members.view_contexts row(s). "
            "Pass --apply to write.",
            scanned,
        )
        return summary

    # Apply: targeted, parameterized DELETE. execute_query(commit=True) returns rowcount.
    deleted = db.execute_query(
        """
        DELETE FROM parameters
        WHERE scope = %s AND namespace = %s AND `key` = %s
        """,
        (_SCOPE, _MEMBERS_NAMESPACE, _VIEW_CONTEXTS_KEY),
        fetch=False,
        commit=True,
    )
    summary["deleted"] = int(deleted or 0)
    logger.info(
        "  OK deleted %d tenant members.view_contexts row(s).", summary["deleted"]
    )

    mode = "DRY RUN" if dry_run else "APPLIED"
    logger.info(
        "\nMigration complete (%s): %d scanned, %d deleted.",
        mode,
        summary["scanned"],
        summary["deleted"],
    )
    return summary


if __name__ == "__main__":
    # Load the backend .env so DB_* / APP_ENV resolve for a manual run (DatabaseManager
    # reads os.getenv and does NOT load .env itself). Best-effort: in a shell that already
    # exported the vars this is a harmless no-op. The target DB is selected by APP_ENV /
    # the DB_* chain (TEST = local Docker, PRODUCTION = Railway) — never hardcoded.
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    except Exception as exc:  # pragma: no cover - .env loading is best-effort
        logger.debug("Skipped .env load (vars may already be set): %s", exc)

    # Dry run is the DEFAULT (R2.1). Require an explicit --apply to write.
    apply = "--apply" in sys.argv
    dry_run = not apply
    if dry_run:
        logger.info("=== DRY RUN MODE (no DB change) — pass --apply to write ===")
    migrate(dry_run=dry_run)
