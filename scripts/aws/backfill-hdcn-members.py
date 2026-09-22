#!/usr/bin/env python3
"""backfill-hdcn-members.py — backfill h-dcn members into ``sam-members`` (S5 task 4.1).

Dry-run-first, non-destructive backfill of h-dcn's Ledenbestand into the NEW tenant-scoped
``sam-members`` table (design "New tenant-scoped tables + backfill" / R5.2 / Property 7).
Reproduces the purpose of h-dcn's historical ``migrationHDCNLedenbestand`` import (the
Google-Sheet Ledenbestand import) against the new module's data model. Mirrors the structure
of the task-4.0 provisioner (``scripts/aws/provision-members-tables.py``): argparse →
resolve → **dry-run plan by default** → ``--apply`` to write → summary.

What it does
------------
1. Reads a READ-ONLY source of raw h-dcn member rows (default: a CSV/JSON export of the
   Google Sheet, via ``sam.members.migration.hdcn_backfill.FileSourceAdapter``). The source is
   NEVER written to.
2. Transforms each row with the pure ``map_hdcn_row`` transform: fixed base (personal +
   membership) + variable overlay (club/Motor details), stamps ``tenant_id = "h-dcn"``,
   normalizes the region onto the plain ``overlay.region`` scope field (S5d D1), maps the
   membership-type value to a catalog ``type_code`` (C8),
   and validates the fixed fields (a bad mapping fails loudly, per-row).
3. In **dry-run (the default)** prints a FIDELITY REPORT — counts, per-field mapping summary,
   validation errors, sample transformed records, and would-be member-number conflicts — and
   writes NOTHING.
4. With ``--apply`` (and only then) persists each transformed record via the repository's
   ``save_member`` (the sole DynamoDB touch-point). Per-tenant member-number uniqueness is the
   repository's conditional write (Property 6): a conflict is REPORTED, never overwritten. A
   re-apply of the same member is the repository's idempotent re-save.

Safety guards (aws-accounts.md guardrails, R5.2)
------------------------------------------------
- **Dry-run is the default.** Nothing is written unless you pass ``--apply``.
- **Non-destructive to the source.** The source adapter is read-only; the live h-dcn data
  stays the source of truth. This script only ever WRITES to ``sam-members`` (never the
  legacy tables), and only under ``--apply``.
- **Fail-fast table/region.** The target table is resolved from ``MEMBERS_TABLE`` via
  ``table_design.resolve_members_table_name()`` (a missing/blank var raises rather than
  guessing). Region defaults to ``eu-west-1`` (aws-accounts.md).
- **Reuses the T0 client.** ``services.dynamodb_client.get_dynamodb_resource`` (local-vs-cloud
  switch via ``AWS_ENDPOINT_URL_DYNAMODB`` + fail-fast) lives in ONE place.

Usage (from repo root, WSL)
---------------------------
  # Dry run (default — writes nothing), fidelity report from a Google-Sheet CSV export.
  # --tenant is REQUIRED (no hardcoded/default tenant):
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --source path/to/hdcn-ledenbestand.csv --tenant h-dcn

  # Actually write to real AWS (nonprofit data account) — only after a clean dry run:
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --source path/to/hdcn-ledenbestand.csv --tenant h-dcn --apply

  # Local emulator apply (endpoint set → local DynamoDB, no real AWS):
  MEMBERS_TABLE=sam-members-local AWS_REGION=eu-west-1 \
      AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --source sam/tests/fixtures/hdcn_ledenbestand_sample.csv --tenant h-dcn --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# repo root + backend/src on sys.path so `sam.members...` and its `services.dynamodb_client`
# dependency both import (mirrors provision-members-tables.py + sam/tests path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.migration.hdcn_backfill import (
    FIXED_SOURCE_COLUMNS,
    HDCN_TENANT_ID,
    BackfillPlan,
    FileSourceAdapter,
    MembershipTypeMapper,
    build_backfill_plan,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
    MemberNumberConflictError,
)

DEFAULT_REGION = "eu-west-1"
#: How many transformed records to show as samples in the fidelity report.
_SAMPLE_COUNT = 3
#: The h-dcn source column that seeds the ``overlay.region`` scope field (mapped, not "unmapped").
_REGION_SOURCE_COLUMN = "regio"


def _classify_source_columns(
    adapter: FileSourceAdapter,
) -> tuple[list[str], list[str]]:
    """Inspect the source header READ-ONLY and split columns into (mapped, unmapped).

    "Mapped" = a column the transform recognizes (a :data:`FIXED_SOURCE_COLUMNS` key or the
    region column). "Unmapped/extra" = every other named column (folded into ``overlay`` by
    ``map_hdcn_row``) plus the empty-named column (dropped). Task 6.2: unmapped/extra export
    columns are OUT of scope — the importer TOLERATES them and LISTS them here; it does not
    individually classify or surface them in the pilot UI. Case-insensitive, mirroring the
    transform's own ``col_lower`` matching. Reads at most the first row (a header probe) — the
    adapter stays read-only and the plan is still built from a fresh read.
    """
    known = set(FIXED_SOURCE_COLUMNS.keys()) | {_REGION_SOURCE_COLUMN}
    columns: list[str] = []
    for row in adapter.rows():
        columns = [str(c) for c in row.keys()]
        break  # a single header probe is enough — no need to walk the whole file
    mapped: list[str] = []
    unmapped: list[str] = []
    for col in columns:
        stripped = col.strip()
        if stripped == "":
            unmapped.append("(empty-named column — dropped)")
        elif stripped.lower() in known:
            mapped.append(stripped)
        else:
            unmapped.append(stripped)
    return mapped, unmapped


def _print_fidelity_report(
    plan: BackfillPlan,
    *,
    apply: bool,
    table_name: str,
    unmapped_columns: list[str] | None = None,
) -> None:
    """Render the dry-run fidelity report (counts, mapping, errors, samples, conflicts)."""
    print("=" * 68)
    print("h-dcn Members backfill — fidelity report")
    print("=" * 68)
    print(f"  tenant        : {plan.tenant_id}")
    print(f"  source        : {plan.source_description}")
    print(f"  target table  : {table_name}")
    print(f"  mode          : {'APPLY (writes via repository)' if apply else 'DRY-RUN (writes nothing)'}")
    print("-" * 68)
    print(f"  source rows   : {plan.source_row_count}")
    print(f"  transformed ok: {plan.ok_count}")
    print(f"  errors        : {plan.error_count}")
    print(f"  missing region: {len(plan.rows_missing_region)}")
    print(f"  dup numbers   : {len(plan.duplicate_member_numbers)} "
          "(would-be uniqueness conflicts within this batch)")

    print("-" * 68)
    print("  per-field mapping summary (count of ok rows carrying each field):")
    summary = plan.field_mapping_summary()
    if not summary:
        print("    (none)")
    for key in sorted(summary):
        print(f"    {key:<28} {summary[key]}")

    print("-" * 68)
    print("  unmapped / extra source columns (OUT of scope — tolerated, not classified):")
    if unmapped_columns:
        for col in unmapped_columns:
            print(f"    {col}  (folded into overlay / dropped)")
    else:
        print("    (none — every source column is a recognized fixed/region column)")

    if plan.duplicate_member_numbers:
        print("-" * 68)
        print("  DUPLICATE member numbers in this batch (repository would reject the 2nd):")
        for number, ids in sorted(plan.duplicate_member_numbers.items()):
            print(f"    number {number!r}: members {ids}")

    if plan.rows_missing_region:
        print("-" * 68)
        print(f"  rows with NO resolved region (overlay.region absent): "
              f"{plan.rows_missing_region}")

    if plan.errors:
        print("-" * 68)
        print("  ROWS THAT FAILED TO MAP (not written; fix the source/mapping and re-run):")
        for member_ref, reasons in plan.errors:
            detail = "; ".join(f"{k}: {v}" for k, v in reasons.items())
            print(f"    row {member_ref!r}: {detail}")

    print("-" * 68)
    print(f"  sample transformed records (first {_SAMPLE_COUNT}):")
    for t in plan.transformed[:_SAMPLE_COUNT]:
        print("    " + json.dumps(t.record, ensure_ascii=False, sort_keys=True))
    print("=" * 68)


def _apply_plan(plan: BackfillPlan, repo: DynamoDbMembersRepository) -> tuple[int, int, list[str]]:
    """Persist each transformed record via ``save_member``. Returns (written, conflicts, notes).

    Conflicts (per-tenant member-number uniqueness, Property 6) are REPORTED, never
    overwritten — a conflicting record is skipped and recorded. An idempotent re-save of the
    same member succeeds (the repository allows it).
    """
    written = 0
    conflicts = 0
    notes: list[str] = []
    for t in plan.transformed:
        try:
            repo.save_member(plan.tenant_id, t.record)
            written += 1
        except MemberNumberConflictError as exc:
            conflicts += 1
            notes.append(
                f"CONFLICT: member {t.member_id!r} number {exc.member_number!r} already "
                f"claimed for tenant {exc.tenant_id!r} — skipped (not overwritten)"
            )
    return written, conflicts, notes


def backfill(
    source_path: str,
    *,
    region: str,
    apply: bool,
    tenant_id: str = HDCN_TENANT_ID,
    fmt: str | None = None,
    known_codes: list[str] | None = None,
    members_config_path: str | None = None,
    repo: DynamoDbMembersRepository | None = None,
) -> int:
    """Run the backfill (dry-run or apply). Returns a process exit code.

    Reads the source READ-ONLY, transforms every row into a :class:`BackfillPlan`, prints the
    fidelity report, and — only if ``apply`` — persists via the repository's ``save_member``.
    The target table name is resolved fail-fast from ``MEMBERS_TABLE``. ``repo`` may be injected
    for tests; in production it is resolved lazily + fail-fast on first write.

    ``tenant_id`` is the administration the records are stamped with. The CLI requires it as an
    explicit ``--tenant`` argument (no hardcoded/default tenant — R8, steering 31); it defaults
    to the pilot literal here only so the S5 task-4.1 call sites and tests keep working.
    """
    # Fail-fast table-name resolution up front (even in dry-run) so a misconfigured target is
    # caught before any transform work — mirrors the provisioner.
    table_name = td.resolve_members_table_name()

    type_mapper = MembershipTypeMapper(known_codes=known_codes) if known_codes else MembershipTypeMapper()

    # A.10/D17: the canonical region vocabulary is TENANT DATA — loaded from the onboarding
    # members-config file (the SAME source that fills `members.scope_dimensions`), NEVER a core
    # constant. Without it, regions are kept verbatim (and would surface as R9.5 offenders), so
    # for a real apply the caller SHOULD pass --members-config so importer + enforcement agree.
    region_canonicalizer = None
    if members_config_path:
        import importlib.util

        _loader_path = os.path.join(
            _REPO_ROOT, "scripts", "aws", "h-dcn", "members_config_loader.py"
        )
        _spec = importlib.util.spec_from_file_location("members_config_loader", _loader_path)
        _loader = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_loader)  # type: ignore[union-attr]
        cfg = _loader.load_members_config(members_config_path)
        region_canonicalizer = _loader.region_canonicalizer(cfg)

    adapter = FileSourceAdapter(source_path, fmt=fmt)
    plan = build_backfill_plan(
        adapter,
        type_mapper=type_mapper,
        tenant_id=tenant_id,
        region_canonicalizer=region_canonicalizer,
    )

    # Classify the source header so the report LISTS the tolerated unmapped/extra columns
    # (task 6.2). A fresh read-only adapter probe — the source is never written.
    _, unmapped_columns = _classify_source_columns(FileSourceAdapter(source_path, fmt=fmt))

    _print_fidelity_report(
        plan, apply=apply, table_name=table_name, unmapped_columns=unmapped_columns
    )

    if not apply:
        print("\nDRY-RUN: no writes made. Review the fidelity report, then re-run with "
              "--apply to persist.")
        return 0

    if plan.error_count:
        # Refuse to write a partially-broken batch: fix the source/mapping first.
        print(f"\nREFUSING --apply: {plan.error_count} row(s) failed to map. Fix them and "
              "re-run (dry-run stays clean before apply).", file=sys.stderr)
        return 2

    repository = repo or DynamoDbMembersRepository()
    written, conflicts, notes = _apply_plan(plan, repository)

    print("\n" + "=" * 68)
    print("Backfill apply summary")
    print("=" * 68)
    print(f"  table     : {table_name}")
    print(f"  written   : {written}")
    print(f"  conflicts : {conflicts} (reported, NOT overwritten)")
    for note in notes:
        print(f"    {note}")
    print("=" * 68)
    # A conflict is a reportable outcome, not a crash — but surface it via a non-zero code so
    # automation notices there was something to reconcile.
    return 0 if conflicts == 0 else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill h-dcn members into the sam-members table. Dry-run by default; "
        "pass --apply to write. Non-destructive to the source.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the READ-ONLY h-dcn export (CSV or JSON — a Google-Sheet export).",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The administration (tenant) the imported records are stamped with (e.g. "
        "'h-dcn'). REQUIRED — there is no hardcoded/default tenant (R8, steering 31): the "
        "script fails if it is missing so nothing can silently land in the wrong partition.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default=None,
        help="Force the source format (default: inferred from the file extension).",
    )
    parser.add_argument(
        "--known-code",
        action="append",
        dest="known_codes",
        default=None,
        help="An expected Lidmaatschap Beheer catalog code (repeatable). When given, the "
        "backfill VALIDATES each mapped membership_type against these (seed via task 4.2). "
        "Omit to run before the catalog exists (any well-formed code is accepted).",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--members-config",
        default=None,
        help="Path to the tenant members-config JSON (e.g. scripts/aws/h-dcn/members_config.json) "
        "— the SAME file that fills members.scope_dimensions. Its region values are the canonical "
        "target the importer normalizes `region` onto (D17: tenant data, not a core constant). "
        "STRONGLY recommended for a real --apply so member regions match the scope grants; if "
        "omitted, regions are kept verbatim (and would surface as R9.5 offenders).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Actually write via the repository. Without this, the script only prints the "
        "fidelity report (dry-run is the default for safety).",
    )
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Explicitly request a dry-run (the DEFAULT): build + render the fidelity report "
        "and write NOTHING. Mutually exclusive with --apply; provided so the safe default can "
        "be stated on the command line.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return backfill(
            args.source,
            region=args.region,
            apply=args.apply,
            tenant_id=args.tenant,
            fmt=args.format,
            known_codes=args.known_codes,
            members_config_path=args.members_config,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
