#!/usr/bin/env python3
"""Members config Phase 2 (step d) — operator cleanup of ``config#views`` projection residue.

``config#views`` is the RETIRED Members ``view_contexts`` column-layout row (Members config
Phase 2, step (d)). No builder emits it any more and nothing reads it, so it can never be
re-created — but a row written BEFORE retirement is ORPHANED: unlike ``scopegrant#...`` rows
(swept by the diff-and-delete reconcile), ``config#*`` rows are **UPSERT-ONLY**, so nothing
sweeps a ``config#views`` row automatically. The only deleter is
``ProjectionSync.delete_config_views_residue`` (backend/src/services/projection_sync.py).

That routine was previously reachable only from its unit tests (no production caller). This
script is its real, runnable entry point: a small, dry-run-by-default, idempotent operator
tool — mirroring the ``--dry-run`` contract of the companion MySQL migration
(``backend/src/migrations/retire_members_view_contexts.py``) that removed the matching
``members.view_contexts`` parameter rows.

What it does (and does NOT do)
------------------------------
- Calls ``delete_config_views_residue(tenants, dry_run=not apply)`` — it addresses the single
  ``config#views`` sort key per tenant and touches NO other record type.
- Tenant-scoped: each tenant's row is read by its own partition key, so no run can cross a
  tenancy boundary (`31` Data Ownership); the tenant list comes from the operator (``--tenants``)
  or the read-only DB source (``--all``), never from a hardcoded literal.
- Idempotent: a tenant with no residue contributes 0 scanned/0 deleted; a re-run after a
  successful apply is a no-op.
- Dry run is the DEFAULT: it only COUNTS the residue. Pass ``--apply`` to actually delete.

Usage
-----
    # dry run (default — no write):
    python scripts/cleanup_config_views_residue.py --tenants h-dcn
    # apply:
    python scripts/cleanup_config_views_residue.py --tenants h-dcn --apply
    # every tenant the read-only DB source knows (dry run):
    python scripts/cleanup_config_views_residue.py --all

Related: steering ``36-config-and-parameters`` (retirement mechanics),
``39-backend-data-access-sam-dynamodb`` (Change-Op / resolved view; single-writer discipline),
and ``.kiro/specs/myBacklog/members-preferred-overview-columns.md`` (F1 decision: keep the
routine and give it a real entry point instead of deleting the only means to clean residue).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence

# ── Path bootstrap (repo root + backend/src) so ``services.*`` imports when run directly,
#    mirroring the sibling operator scripts in this folder. ────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

__all__ = [
    "parse_tenants",
    "cleanup_config_views_residue",
    "main",
]


class _ExplicitTenantSource:
    """Minimal read-only ``SourceProvider`` yielding EXACTLY the tenants given on the CLI.

    The residue cleanup only ever touches ``ProjectionSync.table`` — it never reads the source
    rows. This stub keeps the run free of any database dependency while still satisfying the
    ``SourceProvider`` protocol the sync is constructed with (the tenant list is supplied by the
    operator, never hardcoded).
    """

    def __init__(self, administrations: Sequence[str]) -> None:
        self._administrations = list(administrations)

    def list_administrations(self) -> list[str]:
        """Return the tenants this run was scoped to."""
        return list(self._administrations)

    def get_tenant_source(self, administration: str):  # pragma: no cover - never used here
        """Never called by the residue cleanup (documented seam of the protocol)."""
        raise NotImplementedError("cleanup_config_views_residue never reads source rows")


def parse_tenants(raw: str) -> list[str]:
    """Parse a comma-separated ``--tenants`` value into a clean, de-duplicated list.

    Order-preserving; blank/whitespace-only entries are dropped; a duplicate collapses to its
    first occurrence. An empty/blank input yields an empty list (the caller then falls back to
    ``--all`` or errors out).
    """
    tenants: list[str] = []
    for chunk in (raw or "").split(","):
        name = chunk.strip()
        if name and name not in tenants:
            tenants.append(name)
    return tenants


def cleanup_config_views_residue(
    tenants: Sequence[str],
    *,
    apply: bool = False,
    table=None,
    source=None,
) -> dict[str, int]:
    """Delete the ``config#views`` projection residue for ``tenants`` (dry run by default).

    A thin operator wrapper around ``ProjectionSync.delete_config_views_residue``: it constructs
    the sync (with an explicit-tenants source unless one is injected) and delegates the scoped,
    idempotent, dry-run-by-default delete to it, so the delete mechanics stay in the one place
    that owns them (the sole writer of the projection table) instead of being re-implemented here.

    Args:
        tenants: The administration names to clean. Never hardcoded in this module.
        apply: When False (default) only count the residue; when True delete it.
        table: Optional DynamoDB table double (tests inject an in-memory fake; production leaves
            it ``None`` so the sync resolves the real table fail-fast).
        source: Optional ``SourceProvider`` double (defaults to the explicit-tenants stub).

    Returns:
        ``{"scanned": <rows present>, "deleted": <rows deleted>}`` (``deleted`` is 0 on a dry run).
    """
    from services.projection_sync import ProjectionSync

    sync = ProjectionSync(source or _ExplicitTenantSource(tenants), table=table)
    return sync.delete_config_views_residue(list(tenants), dry_run=not apply)


def _resolve_all_tenants() -> list[str]:
    """Resolve every ``administration`` from the read-only DB source provider (``--all``)."""
    from database import DatabaseManager
    from services._projection_source import DatabaseSourceProvider

    return DatabaseSourceProvider(DatabaseManager()).list_administrations()


def main(argv: Sequence[str] | None = None, *, table=None, source=None) -> int:
    """CLI entry point. ``--dry-run`` behaviour is the DEFAULT; ``--apply`` is required to write."""
    parser = argparse.ArgumentParser(
        description="Delete stored config#views projection residue (dry run by default)."
    )
    parser.add_argument(
        "--tenants",
        default="",
        help="comma-separated administration names to clean (e.g. h-dcn,other)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="resolve every tenant from the read-only DB source instead of --tenants",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually DELETE the residue (default: dry run, count only)",
    )
    args = parser.parse_args(argv)

    tenants = parse_tenants(args.tenants)
    if args.all:
        tenants = _resolve_all_tenants()
    if not tenants:
        parser.error("no tenants: pass --tenants <a,b> or --all")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    summary = cleanup_config_views_residue(
        tenants, apply=args.apply, table=table, source=source
    )
    print(
        f"config#views residue cleanup {'APPLIED' if args.apply else 'DRY RUN'} over "
        f"{len(tenants)} tenant(s): {summary['scanned']} scanned, {summary['deleted']} deleted."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
