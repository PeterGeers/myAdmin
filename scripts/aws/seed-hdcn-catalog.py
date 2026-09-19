#!/usr/bin/env python3
"""seed-hdcn-catalog.py — seed the h-dcn Lidmaatschap Beheer catalog (S5 task 4.2).

Dry-run-first, non-destructive seed of h-dcn's membership types (Erelid / Donateur /
Sponsor / Gewoon lid) into the NEW tenant-scoped ``sam-members`` table as **tenant DATA**
(design C8 / R2.4 / R4.1 Rung 1). The generic Members core stays tenant-agnostic (Property 5):
h-dcn's types live as seed DATA in ``sam.members.migration.hdcn_catalog_seed`` — there is NO
``if tenant == "h-dcn"`` in the module core. Mirrors the structure of the task-4.0 provisioner
and the task-4.1 backfill (``scripts/aws/provision-members-tables.py`` /
``scripts/aws/backfill-hdcn-members.py``): argparse → resolve → **dry-run plan by default** →
``--apply`` to write → summary.

What it does
------------
1. Loads the importable seed DATA (``HDCN_MEMBERSHIP_TYPES``) — a tuple of validated
   ``MembershipTypeEntry`` whose ``type_code``s are the SAME codes the 4.1 backfill emits
   (single source of truth; the seed module asserts coverage at import).
2. Reads the tenant's CURRENT catalog READ-ONLY via ``repo.list_membership_types("h-dcn")``
   and diffs the seed against it (``build_seed_plan``) — classifying each entry as
   *create* / *update* / *unchanged*.
3. In **dry-run (the default)** prints a plan (what exists vs. what WOULD be created/updated)
   and writes NOTHING.
4. With ``--apply`` (and only then) upserts each create/update entry via the repository's
   ``save_membership_type`` (the sole DynamoDB touch-point). ``save`` is an upsert, so a
   re-seed is idempotent — a second apply is all-``unchanged`` and writes nothing.

Safety guards (aws-accounts.md guardrails, C8)
----------------------------------------------
- **Dry-run is the default.** Nothing is written unless you pass ``--apply``.
- **Never destructive.** The seed only ever CREATES/UPDATES catalog entries with
  ``active=True``; it never deactivates or hard-deletes (retiring a type is a soft-delete —
  ``active=False`` — done via a management action, task 5.3, not here). Existing catalog
  entries not in the seed are left untouched.
- **Idempotent.** ``save_membership_type`` is an upsert; re-seeding is safe and reports
  what already exists vs. what it creates.
- **Fail-fast table.** The target table is resolved from ``MEMBERS_TABLE`` via
  ``table_design.resolve_members_table_name()`` (a missing/blank var raises rather than
  guessing). The boto3 client comes from ``services.dynamodb_client.get_dynamodb_resource``
  (used inside ``DynamoDbMembersRepository`` — the single client seam).

Usage (from repo root, WSL)
---------------------------
  # Dry run (default — writes nothing): show what would be seeded for h-dcn:
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/seed-hdcn-catalog.py

  # Actually write to real AWS (nonprofit data account) — only after a clean dry run:
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/seed-hdcn-catalog.py --apply

  # Local emulator apply (endpoint set → local DynamoDB, no real AWS):
  MEMBERS_TABLE=sam-members-test AWS_REGION=eu-west-1 \
      AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
      backend/.venv/bin/python scripts/aws/seed-hdcn-catalog.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# repo root + backend/src on sys.path so `sam.members...` and its `services.dynamodb_client`
# dependency both import (mirrors provision-members-tables.py / backfill-hdcn-members.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.migration.hdcn_catalog_seed import (
    BACKFILL_EMITTABLE_CODES,
    HDCN_MEMBERSHIP_TYPES,
    HDCN_TENANT_ID,
    CatalogSeedPlan,
    build_seed_plan,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

DEFAULT_REGION = "eu-west-1"


def _entry_line(entry) -> str:
    """One-line human rendering of a catalog entry (code, labels, order, active)."""
    label = json.dumps(dict(entry.label), ensure_ascii=False, sort_keys=True)
    return (
        f"{entry.type_code:<14} order={entry.order:<4} active={entry.active!s:<5} {label}"
    )


def _print_seed_plan(plan: CatalogSeedPlan, *, apply: bool, table_name: str) -> None:
    """Render the plan (what exists vs. what would be created/updated). Writes nothing."""
    print("=" * 68)
    print("h-dcn Lidmaatschap Beheer catalog — seed plan")
    print("=" * 68)
    print(f"  tenant        : {plan.tenant_id}")
    print(f"  target table  : {table_name}")
    print(f"  mode          : {'APPLY (writes via repository)' if apply else 'DRY-RUN (writes nothing)'}")
    print("-" * 68)
    print(f"  seed entries  : {len(plan.items)}")
    print(f"  to create     : {len(plan.to_create)}")
    print(f"  to update     : {len(plan.to_update)}")
    print(f"  unchanged     : {len(plan.unchanged)}")
    print(f"  backfill codes: {sorted(BACKFILL_EMITTABLE_CODES)} (all covered by the seed)")

    print("-" * 68)
    print("  entries (action  code / order / active / labels):")
    for item in plan.items:
        print(f"    {item.action.upper():<10} {_entry_line(item.entry)}")
    print("=" * 68)


def _apply_plan(plan: CatalogSeedPlan, repo: DynamoDbMembersRepository) -> tuple[int, int]:
    """Upsert each create/update entry via ``save_membership_type``. Returns (created, updated).

    ``save`` is an upsert, so this is idempotent; ``unchanged`` entries are skipped (nothing
    to write). Never deactivates/deletes — seeding only ever creates/updates active types.
    """
    created = 0
    updated = 0
    for item in plan.items:
        if item.action == "create":
            repo.save_membership_type(plan.tenant_id, item.entry)
            created += 1
        elif item.action == "update":
            repo.save_membership_type(plan.tenant_id, item.entry)
            updated += 1
    return created, updated


def seed(
    *,
    region: str,
    apply: bool,
    repo: DynamoDbMembersRepository | None = None,
) -> int:
    """Run the seed (dry-run or apply). Returns a process exit code.

    Reads the tenant's current catalog READ-ONLY, diffs the seed set into a plan, prints it,
    and — only if ``apply`` — upserts the create/update entries via ``save_membership_type``.
    The target table name is resolved fail-fast from ``MEMBERS_TABLE``. ``repo`` may be
    injected for tests; in production it is resolved lazily + fail-fast on first use.
    """
    # Fail-fast table-name resolution up front (even in dry-run) so a misconfigured target is
    # caught before any work — mirrors the provisioner / backfill.
    table_name = td.resolve_members_table_name()

    repository = repo or DynamoDbMembersRepository()
    existing = repository.list_membership_types(HDCN_TENANT_ID)
    plan = build_seed_plan(existing, seed=HDCN_MEMBERSHIP_TYPES, tenant_id=HDCN_TENANT_ID)

    _print_seed_plan(plan, apply=apply, table_name=table_name)

    if not apply:
        print("\nDRY-RUN: no writes made. Review the plan, then re-run with --apply to seed.")
        return 0

    created, updated = _apply_plan(plan, repository)

    print("\n" + "=" * 68)
    print("Catalog seed apply summary")
    print("=" * 68)
    print(f"  table     : {table_name}")
    print(f"  created   : {created}")
    print(f"  updated   : {updated}")
    print(f"  unchanged : {len(plan.unchanged)} (already present + identical — not rewritten)")
    print("=" * 68)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed the h-dcn Lidmaatschap Beheer catalog (membership types) into the "
        "sam-members table as tenant DATA. Dry-run by default; pass --apply to write. "
        "Idempotent + never destructive.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write via the repository. Without this, the script only prints the "
        "seed plan (dry-run is the default for safety).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return seed(region=args.region, apply=args.apply)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
