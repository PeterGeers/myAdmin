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
   validation errors, sample transformed records, and reused member numbers (a data-quality
   warning) — and writes NOTHING.
4. With ``--apply`` (and only then) persists each transformed record via the repository's
   ``save_member`` (the sole DynamoDB touch-point — a single ``PutItem``). s5k: ``member_number``
   is a plain OPTIONAL string with NO write-time uniqueness guard, so a duplicate number is a
   reported data-quality concern, not a write-time conflict. A re-apply of the same
   ``member_id`` is an idempotent re-save (overwrites its own record).

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

Live direct-read from the Google Sheet (no export file) — operator notes (R6.5)
-------------------------------------------------------------------------------
The `--sheet-id` / `--sheet-name` path reads the Sheet DIRECTLY, READ-ONLY, via a service
account (design D5/D6). Two prerequisites, both MANUAL and gated:

  1. Service-account key ON DISK. Place the EXISTING h-dcn service-account JSON at the shared
     default path (re-download it from Google Cloud if absent — the Sheet is already shared with
     that SA as Viewer), or point at another file with `--credentials`:
         /home/peter/projects/h-dcn/.googleCredentials.json   (DEFAULT_GOOGLE_CREDENTIALS_FILE)
     Scopes requested are read-only: `spreadsheets.readonly` (+ `drive.readonly` ONLY when a
     sheet is resolved by TITLE via `--sheet-name`). The SA never writes the source.
  2. Run against the nonprofit DATA account with the repo `.env` static keys STRIPPED
     (steering 23-aws-accounts: `.env` exports `personal`-account keys + a local DynamoDB
     endpoint that OUTRANK `AWS_PROFILE`, so a plain run silently hits the WRONG account /
     the local emulator). Strip them and let the profile resolve; sanity-check identity FIRST
     (MUST print 506221081911 / NonprofitDeployRole).

  # sanity-check identity (must be 506221081911):
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json

  # dry-run (default — writes nothing) directly from the live Sheet by ID (PREFERRED):
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --sheet-id <SPREADSHEET_ID> --worksheet Ledenbestand --tenant h-dcn

  # insert-only backfill APPLY (after a clean dry-run):
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --sheet-id <SPREADSHEET_ID> --worksheet Ledenbestand --tenant h-dcn --apply

  # RECONCILING sync (match by member_number, upsert, soft-flag absentees status='left'):
  #   dry-run reviews the to-INSERT / to-UPDATE / to-LEAVE / UNMATCHABLE plan; --apply --reconcile
  #   refuses on mapping errors OR duplicate sheet member_number values (R7.7).
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py \
      --sheet-id <SPREADSHEET_ID> --worksheet Ledenbestand --tenant h-dcn --apply --reconcile

`--sheet-name '<title>'` is accepted instead of `--sheet-id` (resolved via a read-only Drive
`files.list`; needs `drive.readonly`; fails on 0 or >1 matches — prefer the ID). NUMBERLESS rows
need NO sheet edit: an empty Lidnummer + an Achternaam becomes a `C_`+Achternaam CONTACT
automatically; a truly empty row is skipped; data with neither is reported UNMATCHABLE.

NOTE — config seed re-run (this spec changed `members_config.json`). The overlay fields
`additional_info` / `deregistration_date` / `termination_date`, the `magazine_pref` /
`payment_method` value changes, and the `member_number` regex (`^(M\d{5}|C_.+)$`) only take
effect in MySQL once `scripts/aws/seed-hdcn-members-config.py` is RE-RUN (onboarding path).
Live confirmation of the actual data read is a MANUAL gated step (needs the credentials file on
disk); it is documented here, not automated in CI (R6.5).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

# repo root + backend/src on sys.path so `sam.members...` and its `services.dynamodb_client`
# dependency both import (mirrors provision-members-tables.py + sam/tests path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.migration.hdcn_backfill import (
    DEFAULT_GOOGLE_CREDENTIALS_FILE,
    HDCN_TENANT_ID,
    BackfillPlan,
    FileSourceAdapter,
    GoogleSheetsSourceAdapter,
    MembershipTypeMapper,
    build_backfill_plan,
    contract_source_columns,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

DEFAULT_REGION = "eu-west-1"
#: How many transformed records to show as samples in the fidelity report.
_SAMPLE_COUNT = 3


def _load_mapping_contract():
    """Load the authored mapping contract (the single-source CSV) via the h-dcn mapping loader.

    Imports ``members_mapping_loader`` BY PATH (it lives under ``scripts/aws/h-dcn/``, not a
    Python package) — mirroring how ``members_config_loader`` is loaded in :func:`backfill` — and
    returns the parsed :class:`MappingContract`. Used to derive the "mapped" source-column set for
    :func:`_classify_source_columns` so the fidelity report classifies against the CSV, not a
    stale dict (s5m R0.1/R0.4).
    """
    import importlib.util

    hdcn_dir = os.path.join(_REPO_ROOT, "scripts", "aws", "h-dcn")
    # The mapping loader imports its sibling ``members_config_loader`` for the drift guard, so the
    # onboarding scripts dir must be importable while we load it.
    if hdcn_dir not in sys.path:
        sys.path.insert(0, hdcn_dir)
    module = sys.modules.get("members_mapping_loader")
    if module is None:
        loader_path = os.path.join(hdcn_dir, "members_mapping_loader.py")
        spec = importlib.util.spec_from_file_location("members_mapping_loader", loader_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["members_mapping_loader"] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.load_mapping_contract()


def _base_header(column: str) -> str:
    """Strip a trailing ``#<colindex>`` position suffix back to the BASE header (spec R1.3).

    Mirrors the transform's own base-header matching so a position-tracked duplicate
    (``E-mailadres#34``) is classified by the SAME rule as its bare sibling.
    """
    if "#" in column:
        head, _, tail = column.rpartition("#")
        if tail.isdigit():
            return head
    return column


def _classify_source_columns(
    adapter: FileSourceAdapter | GoogleSheetsSourceAdapter,
    known_columns: set[str],
) -> tuple[list[str], list[str]]:
    """Inspect the source header READ-ONLY and split columns into (mapped, unmapped).

    "Mapped" = a column the loaded MAPPING CONTRACT declares a target for (a fixed
    ``personal.*``/``membership.*`` source column or an ``overlay.*`` source column, incl. the
    region column). ``known_columns`` is exactly that set (BASE headers, lower-cased), sourced
    from :func:`sam.members.migration.hdcn_backfill.contract_source_columns` on the loaded
    contract — the SINGLE authored CSV, never a stale in-code dict (s5m R0.1/R0.4). "Unmapped/
    extra" = every other named column (a disposition column, or an unmapped-but-kept column
    folded into ``overlay.additional_info`` by ``map_hdcn_row``) plus the empty-named column
    (dropped). Task 6.2: unmapped/extra export columns are OUT of scope — the importer TOLERATES
    them and LISTS them here. Case-insensitive and base-header matched, mirroring the transform's
    own matching. Reads at most the first row (a header probe) — the adapter stays read-only and
    the plan is still built from a fresh read.
    """
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
        elif _base_header(stripped).lower() in known_columns:
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
    """Render the dry-run fidelity report (counts, mapping, errors, samples, dup-number warning)."""
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
    print(f"  skipped (empty): {plan.skipped_count} "
          "(empty/spacer rows — no meaningful data — excluded, NOT errors)")
    print(f"  missing region: {len(plan.rows_missing_region)}")
    print(f"  dup numbers   : {len(plan.duplicate_member_numbers)} "
          "(member numbers reused within this batch — data-quality warning)")

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
        print("  DUPLICATE member numbers in this batch (data-quality warning — resolve in source):")
        for number, ids in sorted(plan.duplicate_member_numbers.items()):
            print(f"    number {number!r}: members {ids}")

    if plan.rows_missing_region:
        print("-" * 68)
        print(f"  rows with NO resolved region (overlay.region absent): "
              f"{plan.rows_missing_region}")

    if plan.skipped:
        print("-" * 68)
        print("  SKIPPED rows (empty/spacer — no meaningful data — deliberately excluded, NOT errors):")
        for label, reason in plan.skipped:
            print(f"    {label!r}: {reason}")

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


def _apply_plan(plan: BackfillPlan, repo: DynamoDbMembersRepository) -> int:
    """Persist each transformed record via ``save_member``. Returns the count written.

    s5k: ``save_member`` is a single ``PutItem`` — ``member_number`` is a plain OPTIONAL string
    with NO write-time uniqueness guard (a duplicate is a data-quality concern, not a conflict).
    An idempotent re-save of the same ``member_id`` overwrites its own record.
    """
    written = 0
    for t in plan.transformed:
        repo.save_member(plan.tenant_id, t.record)
        written += 1
    return written


# ── Reconciling sync (match by member_number, upsert, absence sweep) — s5m Task 7 / D7 ─

#: The soft-flag status stamped on a SAM record whose ``member_number`` is ABSENT from the
#: current sheet (R7.4 / R5.2). It is the closed :class:`MembershipStatus` value ``left`` ("nl:
#: Uitgeschreven") — a SOFT flag written via ``save_member``; the sync NEVER ``delete_member``s.
_LEFT_STATUS = "left"


def _member_number_of(record) -> str:
    """Return a record's ``membership.member_number`` (``M…``/``C_…``), or ``""`` if absent."""
    return str((record.get("membership") or {}).get("member_number") or "")


@dataclass
class ReconcilePlan:
    """The result of reconciling a sheet against the current SAM partition (dry-run or apply).

    Drives the upsert + absence sweep (D7/R7): every sheet candidate is classified INSERT (its
    number is new to SAM), UPDATE (its number matches an existing SAM record — the existing
    ``member_id`` is reused, sheet-wins on mapped fields), or UNMATCHABLE (no ``member_number``
    could be derived — reported, never written). Any SAM record whose number was NOT seen in the
    sheet this run is swept to ``status = "left"`` (soft flag, R7.4). Duplicate sheet numbers and
    duplicate SAM numbers are collected so ``--apply`` can refuse (R7.6/R7.7).
    """

    tenant_id: str
    #: (member_number, record-to-save-with-reused-member_id) — an existing SAM record updated.
    to_update: list[tuple[str, dict]] = field(default_factory=list)
    #: (member_number, record-to-save) — a new SAM record (its minted member_id kept).
    to_insert: list[tuple[str, dict]] = field(default_factory=list)
    #: (member_number, member_id, record-to-save) — an existing SAM record soft-flagged ``left``.
    to_leave: list[tuple[str, str, dict]] = field(default_factory=list)
    #: candidate records that derived NO member_number — reported, not written (R7.2/R7.3).
    unmatchable: list[dict] = field(default_factory=list)
    #: sheet member_numbers appearing on more than one candidate this run (a matching hazard).
    duplicate_sheet_numbers: dict[str, int] = field(default_factory=dict)
    #: SAM member_numbers carried by more than one existing record (reported for reconciliation).
    duplicate_sam_numbers: dict[str, list[str]] = field(default_factory=dict)
    #: existing SAM member_ids with a BLANK member_number — cannot be matched by number (R7.5).
    blank_number_members: list[str] = field(default_factory=list)


def _index_sam_by_number(
    repo: DynamoDbMembersRepository, tenant_id: str
) -> tuple[dict[str, dict], dict[str, list[str]], list[str]]:
    """Read the tenant's members once and index them by ``member_number`` (D7 step 1 / R7.5).

    The repository exposes no query-by-number, so this is an in-memory index over a single
    ``list_members`` read. Returns ``(by_number, duplicate_sam_numbers, blank_number_members)``:
    ``by_number`` maps each non-blank ``member_number`` to its (first-seen) SAM record; a number
    carried by more than one record is also collected into ``duplicate_sam_numbers`` (reported);
    a record with a BLANK number cannot be matched and its ``member_id`` is bucketed separately
    (R7.5). Members AND ``C_`` contacts are indexed identically.
    """
    by_number: dict[str, dict] = {}
    owners: dict[str, list[str]] = {}
    blank: list[str] = []
    for member in repo.list_members(tenant_id):
        number = _member_number_of(member)
        member_id = str(member.get("member_id") or "")
        if not number:
            blank.append(member_id)
            continue
        owners.setdefault(number, []).append(member_id)
        # First-seen wins as the match target; a duplicate is reported (below), not overwritten.
        by_number.setdefault(number, dict(member))
    duplicate_sam_numbers = {n: ids for n, ids in owners.items() if len(ids) > 1}
    return by_number, duplicate_sam_numbers, blank


def build_reconcile_plan(
    plan: BackfillPlan,
    repo: DynamoDbMembersRepository,
    tenant_id: str,
) -> ReconcilePlan:
    """Reconcile the transformed sheet candidates against the current SAM partition (D7/R7).

    Classifies every candidate as INSERT / UPDATE / UNMATCHABLE on its DERIVED ``member_number``
    (R7.3), reusing the existing ``member_id`` on an UPDATE so re-runs are idempotent (R5.3), then
    sweeps any SAM record whose number was NOT seen this run to ``status = "left"`` (soft flag,
    R7.4 — members AND contacts). SHEET-WINS: an UPDATE saves the sheet-derived record (its mapped
    fields overwrite SAM), keeping only the existing internal ``member_id`` (R7.3). Duplicate sheet
    numbers and duplicate/blank SAM numbers are collected for the report / ``--apply`` refusal.
    """
    result = ReconcilePlan(tenant_id=tenant_id)
    by_number, result.duplicate_sam_numbers, result.blank_number_members = _index_sam_by_number(
        repo, tenant_id
    )

    seen_counts: dict[str, int] = {}
    seen_numbers: set[str] = set()
    for cand in plan.transformed:
        record = dict(cand.record)
        number = _member_number_of(record)
        if not number:
            # A candidate that derived no member_number is UNMATCHABLE (R7.2/R7.3): reported,
            # never written. (In practice the required last_name usually makes such a row fail
            # to map upstream; this catches any that still transform without a key.)
            result.unmatchable.append(record)
            continue
        seen_counts[number] = seen_counts.get(number, 0) + 1
        seen_numbers.add(number)
        existing = by_number.get(number)
        if existing is not None:
            # UPDATE: reuse the existing internal member_id (SHEET-WINS on the mapped fields).
            record["member_id"] = existing.get("member_id")
            result.to_update.append((number, record))
        else:
            # INSERT: the candidate's freshly-minted member_id is kept.
            result.to_insert.append((number, record))

    result.duplicate_sheet_numbers = {n: c for n, c in seen_counts.items() if c > 1}

    # Absence sweep (R7.4): any SAM record whose number was NOT seen in the sheet this run is
    # soft-flagged `left`. Members AND C_ contacts are included. A record already `left` and gone
    # from the sheet is re-flagged idempotently; one present in the sheet is reactivated via its
    # (INSERT/UPDATE) sheet-derived record above.
    for number, member in by_number.items():
        if number in seen_numbers:
            continue
        swept = dict(member)
        membership = dict(swept.get("membership") or {})
        membership["status"] = _LEFT_STATUS
        swept["membership"] = membership
        result.to_leave.append((number, str(member.get("member_id") or ""), swept))

    return result


def _print_reconcile_report(recon: ReconcilePlan) -> None:
    """Render the sync sections of the fidelity report (R7.6): INSERT/UPDATE/LEAVE/UNMATCHABLE."""
    print("-" * 68)
    print("  RECONCILE (sync) plan — match by member_number, upsert + soft-flag absence:")
    print(f"    to-INSERT (new number)      : {len(recon.to_insert)}")
    print(f"    to-UPDATE (matched number)  : {len(recon.to_update)}")
    print(f"    to-LEAVE  (soft-flag left)  : {len(recon.to_leave)}")
    print(f"    UNMATCHABLE (no number)     : {len(recon.unmatchable)}")
    print(f"    blank SAM numbers (R7.5)    : {len(recon.blank_number_members)}")

    if recon.to_leave:
        print("-" * 68)
        print("  SAM records ABSENT from the sheet → soft-flag status='left' (NOT deleted, R7.4):")
        for number, member_id, _rec in sorted(recon.to_leave):
            print(f"    {number}  (member_id {member_id})")

    if recon.unmatchable:
        print("-" * 68)
        print("  UNMATCHABLE sheet rows (no member_number derivable — NOT written, R7.2):")
        for rec in recon.unmatchable:
            personal = rec.get("personal") or {}
            label = " ".join(
                str(personal.get(k, "")).strip() for k in ("first_name", "last_name")
            ).strip()
            print(f"    {label or '<empty>'}")

    if recon.duplicate_sheet_numbers:
        print("-" * 68)
        print("  DUPLICATE member_number in the SHEET (blocks --apply --reconcile, R7.7):")
        for number, count in sorted(recon.duplicate_sheet_numbers.items()):
            print(f"    {number!r}: {count} rows")

    if recon.duplicate_sam_numbers:
        print("-" * 68)
        print("  DUPLICATE member_number already in SAM (reconcile in the source, R7.6):")
        for number, ids in sorted(recon.duplicate_sam_numbers.items()):
            print(f"    {number!r}: members {ids}")


def _apply_reconcile_plan(recon: ReconcilePlan, repo: DynamoDbMembersRepository) -> dict[str, int]:
    """Apply the reconcile plan: UPSERT candidates + soft-flag absent records (D7/R7.3/R7.4).

    Every write is a single ``save_member`` (s5k — no guard). Returns a counts dict
    ``{inserted, updated, left}``. NEVER calls ``delete_member`` (R5.2): an absent record is only
    soft-flagged ``status='left'``.
    """
    counts = {"inserted": 0, "updated": 0, "left": 0}
    for _number, record in recon.to_insert:
        repo.save_member(recon.tenant_id, record)
        counts["inserted"] += 1
    for _number, record in recon.to_update:
        repo.save_member(recon.tenant_id, record)
        counts["updated"] += 1
    for _number, _member_id, record in recon.to_leave:
        repo.save_member(recon.tenant_id, record)
        counts["left"] += 1
    return counts


def _build_source_adapter(
    source_path: str | None,
    *,
    fmt: str | None = None,
    sheet_id: str | None = None,
    sheet_name: str | None = None,
    worksheet: str | None = None,
    credentials_file: str = DEFAULT_GOOGLE_CREDENTIALS_FILE,
) -> FileSourceAdapter | GoogleSheetsSourceAdapter:
    """Build the READ-ONLY source adapter selected by the CLI flags (design D6, R4.6).

    A Google Sheet is requested when ``sheet_id`` OR ``sheet_name`` is given → a
    :class:`GoogleSheetsSourceAdapter` reading the live Sheet DIRECTLY (READ-ONLY, R5.1): the id
    from the URL is used as-is (preferred), a title is resolved via a read-only Drive lookup, an
    optional ``worksheet`` tab becomes the A1 range prefix, and ``credentials_file`` is the
    service-account key path (default the shared h-dcn key). Otherwise a
    :class:`FileSourceAdapter` over the ``--source`` export, as before. A fresh adapter is built
    per call so the header-probe and the plan each read the source independently (never written).
    """
    if sheet_id or sheet_name:
        return GoogleSheetsSourceAdapter(
            spreadsheet_id=sheet_id,
            spreadsheet_name=sheet_name,
            worksheet=worksheet,
            credentials_file=credentials_file,
        )
    if not source_path:
        raise ValueError(
            "No source given: pass --source <file>, or --sheet-id / --sheet-name for a live "
            "Google Sheet."
        )
    return FileSourceAdapter(source_path, fmt=fmt)


def backfill(
    source_path: str | None = None,
    *,
    region: str,
    apply: bool,
    reconcile: bool = False,
    tenant_id: str = HDCN_TENANT_ID,
    fmt: str | None = None,
    sheet_id: str | None = None,
    sheet_name: str | None = None,
    worksheet: str | None = None,
    credentials_file: str = DEFAULT_GOOGLE_CREDENTIALS_FILE,
    known_codes: list[str] | None = None,
    members_config_path: str | None = None,
    repo: DynamoDbMembersRepository | None = None,
) -> int:
    """Run the backfill (dry-run or apply). Returns a process exit code.

    Reads the source READ-ONLY, transforms every row into a :class:`BackfillPlan`, prints the
    fidelity report, and — only if ``apply`` — persists via the repository's ``save_member``.
    The target table name is resolved fail-fast from ``MEMBERS_TABLE``. ``repo`` may be injected
    for tests; in production it is resolved lazily + fail-fast on first write.

    The source is either a file export (``source_path``/``--source``) or a live Google Sheet
    (``sheet_id``/``sheet_name`` + optional ``worksheet``/``credentials_file``) — the SAME adapter
    type is used for the header-probe and the plan (design D6/R4.6). Everything downstream
    (:func:`build_backfill_plan`, :func:`_apply_plan`, the report, the ``--apply`` refusal on
    mapping errors) is adapter-agnostic and unchanged.

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

    _adapter_kwargs = dict(
        fmt=fmt,
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        worksheet=worksheet,
        credentials_file=credentials_file,
    )
    adapter = _build_source_adapter(source_path, **_adapter_kwargs)
    plan = build_backfill_plan(
        adapter,
        type_mapper=type_mapper,
        tenant_id=tenant_id,
        region_canonicalizer=region_canonicalizer,
    )

    # Classify the source header so the report LISTS the tolerated unmapped/extra columns
    # (task 6.2). The "known/mapped" column set comes from the loaded MAPPING CONTRACT — the
    # single authored CSV — NOT a stale in-code dict, so the report judges mapped-vs-unmapped
    # against the same source of truth the transform uses (s5m R0.1/R0.4). A fresh read-only
    # adapter probe — the source is never written.
    known_columns = contract_source_columns(_load_mapping_contract())
    _, unmapped_columns = _classify_source_columns(
        _build_source_adapter(source_path, **_adapter_kwargs), known_columns
    )

    _print_fidelity_report(
        plan, apply=apply, table_name=table_name, unmapped_columns=unmapped_columns
    )

    # ── Reconciling sync (--reconcile/--sync): match by member_number, upsert + absence sweep.
    # Additive — without --reconcile the runner keeps its insert-only backfill behaviour (below).
    if reconcile:
        repository = repo or DynamoDbMembersRepository()
        recon = build_reconcile_plan(plan, repository, tenant_id)
        _print_reconcile_report(recon)

        if not apply:
            print("\nDRY-RUN (reconcile): no writes made. Review the sync plan, then re-run "
                  "with --apply --reconcile to upsert + soft-flag.")
            return 0

        # Refuse (write nothing) on any mapping error (existing rule) OR duplicate sheet numbers
        # (a matching hazard — "which record does this update?" is ambiguous), R7.7.
        if plan.error_count:
            print(f"\nREFUSING --apply --reconcile: {plan.error_count} row(s) failed to map. "
                  "Fix them and re-run.", file=sys.stderr)
            return 2
        if recon.duplicate_sheet_numbers:
            dupes = ", ".join(sorted(recon.duplicate_sheet_numbers))
            print(f"\nREFUSING --apply --reconcile: the sheet has duplicate member_number(s) "
                  f"[{dupes}] — resolve the duplicate in the source first (R7.7).",
                  file=sys.stderr)
            return 2

        counts = _apply_reconcile_plan(recon, repository)
        print("\n" + "=" * 68)
        print("Reconcile apply summary")
        print("=" * 68)
        print(f"  table     : {table_name}")
        print(f"  inserted  : {counts['inserted']}")
        print(f"  updated   : {counts['updated']}")
        print(f"  left      : {counts['left']}  (soft-flagged; never deleted)")
        print("=" * 68)
        return 0

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
    written = _apply_plan(plan, repository)

    print("\n" + "=" * 68)
    print("Backfill apply summary")
    print("=" * 68)
    print(f"  table     : {table_name}")
    print(f"  written   : {written}")
    print("=" * 68)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill h-dcn members into the sam-members table. Dry-run by default; "
        "pass --apply to write. Non-destructive to the source.",
    )
    # Source-selection group (design D6/R4.6): EXACTLY ONE of a file export (--source) OR a live
    # Google Sheet (--sheet-id / --sheet-name). --worksheet + --credentials accompany the sheet
    # options. --sheet-id is preferred (unambiguous, no Drive lookup); --sheet-name resolves the
    # title via a read-only Drive files.list (needs the drive.readonly scope).
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source",
        help="Path to the READ-ONLY h-dcn export (CSV or JSON — a Google-Sheet export). Mutually "
        "exclusive with --sheet-id/--sheet-name.",
    )
    source_group.add_argument(
        "--sheet-id",
        dest="sheet_id",
        help="Google Sheet spreadsheet ID from the URL "
        "(.../spreadsheets/d/<ID>/edit) — read DIRECTLY, READ-ONLY, no Drive lookup. PREFERRED "
        "(unambiguous). Mutually exclusive with --source/--sheet-name.",
    )
    source_group.add_argument(
        "--sheet-name",
        dest="sheet_name",
        help="Google Sheet human title (e.g. 'HDCN Ledenbestand 2026') — resolved to an ID via a "
        "READ-ONLY Drive files.list (fails if 0 or >1 sheets match; prefer --sheet-id). Mutually "
        "exclusive with --source/--sheet-id.",
    )
    parser.add_argument(
        "--worksheet",
        default=None,
        help="Tab name within the Sheet (e.g. 'Ledenbestand') → A1 range prefix "
        "\"'<worksheet>'!A1:ZZ\". Omit for the default/first sheet. Only used with "
        "--sheet-id/--sheet-name.",
    )
    parser.add_argument(
        "--credentials",
        dest="credentials",
        default=DEFAULT_GOOGLE_CREDENTIALS_FILE,
        help="Filesystem PATH to the service-account JSON key used to READ the Sheet (default: "
        f"the shared h-dcn key {DEFAULT_GOOGLE_CREDENTIALS_FILE}). Only used with "
        "--sheet-id/--sheet-name.",
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
    parser.add_argument(
        "--reconcile",
        "--sync",
        dest="reconcile",
        action="store_true",
        help="Run as a RECONCILING SYNC (match by member_number, upsert, and soft-flag records "
        "absent from the sheet as status='left' — never delete). ADDITIVE: without it the "
        "runner keeps its insert-only backfill behaviour (R7.1). Dry-run stays the default; "
        "--apply --reconcile writes and refuses on mapping errors OR duplicate sheet numbers.",
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
            reconcile=args.reconcile,
            tenant_id=args.tenant,
            fmt=args.format,
            sheet_id=args.sheet_id,
            sheet_name=args.sheet_name,
            worksheet=args.worksheet,
            credentials_file=args.credentials,
            known_codes=args.known_codes,
            members_config_path=args.members_config,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
