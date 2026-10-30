#!/usr/bin/env python3
"""
03a C6 HARD GATE — all-tenant zero-un-migrated-`choices` scan (BLOCKING deployment step).

This is the explicit, BLOCKING verification that gates C6 fail-loud going live (design 03a
"Hard gate before C6 goes live" / "Deployment ordering" §4). Fail-loud must NOT be enabled until
an all-tenant scan confirms ZERO un-migrated bare-``choices`` rows remain — NOT "essentially one
row" by assumption. A single missed un-migrated row is an OUTAGE under fail-loud: the staff
config-editor read RAISES and the public application read DROPS a real field. The staff-raise /
public-drop blast-radius split (task 9 / C6) BOUNDS that outage but does NOT remove this gate.

What it does (READ-ONLY — it never writes)
-------------------------------------------
For EVERY tenant it reads the stored ``config#fields`` row and enumerates every field/override
ENTRY that still carries a bare ``choices`` attribute (vocabulary under the legacy key, in either
the ``fields.*`` or ``overrides.*`` map). It COUNTS the offenders and prints a clear
per-tenant/per-field report. Its exit code is the gate:

    exit 0  — PASS: zero bare-`choices` entries across all scanned tenants (C7 backfill confirmed
              complete tenant-wide; C6 fail-loud is safe to enable).
    exit 1  — FAIL (BLOCKING): at least one un-migrated bare-`choices` entry remains. Enabling C6
              fail-loud now would trip on that row in production. Run the C7 backfill
              (``scripts/migrate_config_fields_choices_to_options.py``) for the named tenant(s)
              and re-run this scan until it is green.

This is an EXPLICIT SCAN, not an inference — it reads the live rows and counts, it does not reason
"there is probably only one row".

Reuse of the C7 enumerator (single source of truth for "what is a bare-`choices` entry")
----------------------------------------------------------------------------------------
Finding an offender is EXACTLY the C7 migration planner's enumeration: a bare-``choices`` entry is
one the C7 backfill would rewrite. So this scan imports and reuses
:func:`scripts.migrate_config_fields_choices_to_options.plan_choices_to_options` — the pure,
storage-agnostic enumerator — rather than re-deriving the "what counts as un-migrated" predicate.
If that predicate ever changes, both the migration and this gate move together, by construction.

Enumeration approach — how "EVERY tenant" is resolved (documented, deliberate)
------------------------------------------------------------------------------
The SAM-plane reader (:class:`MembersProjectionReader`) is PARTITION-KEYED by ``tenant_id`` — every
read is one ``Query`` on a single tenant partition, and steering 39 forbids a cross-tenant
``.scan()`` IN the repository layer (tenant isolation is the whole point of the partition key).
There is therefore NO cross-tenant enumeration primitive on the reader, and adding one to the
repository layer is out of scope for this gate (and would weaken the isolation invariant).

Two enumeration sources are supported; both then go through the SAME per-tenant resolved read
(``reader.get_raw_fields_overlay``) + the SAME C7 enumerator, so the offender predicate is
identical regardless of how the tenant set was discovered:

  1. **Explicit tenant list** (``--tenant`` / ``--tenants-file``) — the operator supplies the set
     of tenants to scan. Preferred when the tenant roster is known (the deploy runbook names it).
     This keeps the scan entirely on the partition-keyed resolved read path.

  2. **Operator-level table discovery** (``--all``, the default when no list is given) — this
     script is an OPERATOR tool, not product code (exactly like the C7 migration script, which is
     allowed to be its own composition root). In this mode the script's composition root performs
     a ONE-SHOT, READ-ONLY table ``scan`` of the projection table to DISCOVER which tenants have a
     ``config#fields`` row, then hands each discovered ``tenant_id`` back through the normal
     partition-keyed ``reader.get_raw_fields_overlay`` resolved read for the actual offender check.
     The discovery scan lives HERE in the operator script's composition root — NOT in the
     repository layer — so the repository's "no cross-tenant scan" rule is intact. (A tenant
     DIRECTORY projection could replace this discovery scan if/when one is available; the gate's
     offender check would be unchanged.)

Layering (steering 39)
----------------------
Like the C7 migration script, this operator script is allowed to construct the boto3-backed
reader (the composition root ``app.py`` would otherwise provide) and, in ``--all`` mode, to run
the one-shot discovery ``scan``. The OFFENDER CHECK itself never touches raw boto3: it goes through
``MembersProjectionReader.get_raw_fields_overlay`` (the resolved read) + the pure C7 enumerator.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# ── Path bootstrap (repo root + backend/src) so ``sam.*`` / ``services.*`` import when the
#    script is run directly, mirroring the C7 migration script's bootstrap. ──────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

__all__ = [
    "Offender",
    "TenantScanResult",
    "scan_overlay",
    "scan_tenant",
    "scan_tenants",
    "main",
]


# ── Reuse the C7 pure enumerator as the single source of the "bare-`choices`" predicate ─────
def _load_c7_planner():
    """Import ``plan_choices_to_options`` from the C7 migration script.

    The migration lives under ``scripts/`` (not an importable package), so load it by file path
    exactly as its own unit test does. We reuse its PURE enumerator so "what is an un-migrated
    bare-`choices` entry" is defined in ONE place.
    """
    path = os.path.join(_REPO_ROOT, "scripts", "migrate_config_fields_choices_to_options.py")
    spec = importlib.util.spec_from_file_location(
        "migrate_config_fields_choices_to_options", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_c7 = _load_c7_planner()
plan_choices_to_options = _c7.plan_choices_to_options


# ── Result shapes ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Offender:
    """One un-migrated bare-``choices`` entry found in a tenant's ``config#fields`` row.

    - ``tenant_id`` — the tenant whose row carries the offender.
    - ``map_name`` — ``"fields"`` (a tenant variable field) or ``"overrides"`` (a fixed-field
      override), the storage map the entry lives in.
    - ``entry_key`` — the entry's key within that map (bare key, or dotted ``<group>.<key>`` for
      an override).
    """

    tenant_id: str
    map_name: str
    entry_key: str


@dataclass(frozen=True)
class TenantScanResult:
    """The outcome of scanning ONE tenant's ``config#fields`` row."""

    tenant_id: str
    offenders: tuple[Offender, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.offenders


# ── Pure scan core (no boto3 — unit-testable in isolation over the stored overlay shape) ────


def scan_overlay(tenant_id: str, overlay: Mapping) -> TenantScanResult:
    """Enumerate the bare-``choices`` offenders in ONE tenant's stored overlay (pure).

    ``overlay`` is the at-rest ``config#fields`` shape — ``{"fields": {...}, "overrides": {...}}``
    (the storage key is ``overrides``, mapped from the reader's wire key ``fixed_overrides`` by
    :func:`scan_tenant`). Delegates the offender predicate to the C7 planner so the definition of
    "un-migrated" is shared with the migration, then records each planned entry as an
    :class:`Offender`. A clean tenant (every selectable field on ``options``, no ``choices``)
    yields zero offenders.
    """
    plans = plan_choices_to_options(overlay)
    offenders = tuple(
        Offender(tenant_id=tenant_id, map_name=p.map_name, entry_key=p.entry_key)
        for p in plans
    )
    return TenantScanResult(tenant_id=tenant_id, offenders=offenders)


# ── The live driver (reads each tenant's resolved overlay; counts offenders; reports) ───────


def scan_tenant(tenant_id: str, *, reader) -> TenantScanResult:
    """Read one tenant's ``config#fields`` row (resolved) and scan it for bare-``choices`` entries.

    ``reader`` exposes ``get_raw_fields_overlay(tenant_id, *, consistent_read=True)`` returning the
    stored overlay in the authoring WIRE shape (``overrides`` served under ``fixed_overrides``).
    The read is STRONGLY-CONSISTENT so a just-run C7 backfill is reflected (the gate must not pass
    on a stale view). READ-ONLY. A missing row → an empty overlay → a clean result.
    """
    wire = reader.get_raw_fields_overlay(tenant_id, consistent_read=True)
    # Map the wire shape (fixed_overrides) back to the at-rest shape the C7 enumerator expects
    # (overrides) — the same alignment the C7 migration driver does.
    overlay = {
        "fields": wire.get("fields") or {},
        "overrides": wire.get("fixed_overrides") or {},
    }
    return scan_overlay(tenant_id, overlay)


def scan_tenants(tenant_ids: Sequence[str], *, reader, out=None) -> list[TenantScanResult]:
    """Scan EVERY tenant in ``tenant_ids`` and print a per-tenant/per-field report.

    Returns one :class:`TenantScanResult` per tenant (so a caller / test can assert the outcome).
    The printed report names every offender tenant→map.entry so an operator can run the C7
    backfill for exactly those tenants.
    """
    out = out if out is not None else sys.stdout
    results: list[TenantScanResult] = []
    for tenant_id in tenant_ids:
        result = scan_tenant(tenant_id, reader=reader)
        results.append(result)
        if result.clean:
            print(f"[{tenant_id}] OK — no bare-`choices` entries.", file=out)
        else:
            for off in result.offenders:
                print(
                    f"[{tenant_id}] UN-MIGRATED: {off.map_name}.{off.entry_key} "
                    f"still carries bare `choices` (C7 backfill not applied).",
                    file=out,
                )
    return results


def _print_summary(results: Sequence[TenantScanResult], *, out=None) -> int:
    """Print the gate verdict and return the process exit code (0 PASS / 1 FAIL)."""
    out = out if out is not None else sys.stdout
    total_offenders = sum(len(r.offenders) for r in results)
    offender_tenants = [r.tenant_id for r in results if not r.clean]
    scanned = len(results)
    if total_offenders == 0:
        print(
            f"\nPASS — scanned {scanned} tenant(s); ZERO un-migrated bare-`choices` entries. "
            f"C6 fail-loud is safe to enable.",
            file=out,
        )
        return 0
    print(
        f"\nFAIL (BLOCKING) — scanned {scanned} tenant(s); found {total_offenders} un-migrated "
        f"bare-`choices` entr{'y' if total_offenders == 1 else 'ies'} across "
        f"{len(offender_tenants)} tenant(s): {', '.join(offender_tenants)}.\n"
        f"Run scripts/migrate_config_fields_choices_to_options.py for those tenant(s), then "
        f"re-run this scan. C6 fail-loud MUST NOT be enabled until this gate is green.",
        file=out,
    )
    return 1


# ── Composition root + tenant discovery (operator-level; NOT the repository layer) ──────────


def _build_reader(table=None):
    """Compose the boto3-backed resolved reader for a live run (the operator composition root).

    This is what ``app.py`` would otherwise provide. The table resolves fail-fast from
    ``GOVERNANCE_PROJECTION_TABLE`` inside the reader; a ``table`` may be injected (tests /
    a local-DynamoDB run).
    """
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    return MembersProjectionReader(table=table)


def _discover_tenants_with_config_fields(table=None) -> list[str]:
    """Operator-level ONE-SHOT, READ-ONLY discovery of tenants carrying a ``config#fields`` row.

    Performs a projection-table ``scan`` HERE in the operator script's composition root — NOT in
    the repository layer — to enumerate which ``tenant_id`` partitions have a ``config#fields``
    sort key. The actual offender check still goes through the per-tenant resolved read
    (:func:`scan_tenant`), so the repository's "no cross-tenant scan" rule is preserved: the scan
    only DISCOVERS the tenant set, it does not read the vocabulary.

    Returns a sorted, de-duplicated list of ``tenant_id`` values. Paginates the scan so a large
    table is fully covered.
    """
    from services import projection_schema as schema

    tbl = table if table is not None else schema.get_projection_table_resource()
    config_fields_sk = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)

    tenants: set[str] = set()
    scan_kwargs: dict = {
        "ProjectionExpression": "#pk, #sk",
        "ExpressionAttributeNames": {
            "#pk": schema.PARTITION_KEY_ATTR,
            "#sk": schema.SORT_KEY_ATTR,
        },
    }
    while True:
        response = tbl.scan(**scan_kwargs)
        for item in response.get("Items", []) or []:
            if item.get(schema.SORT_KEY_ATTR) == config_fields_sk:
                tenant_id = item.get(schema.PARTITION_KEY_ATTR)
                if tenant_id:
                    tenants.add(tenant_id)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(tenants)


def _resolve_tenant_ids(args, *, table=None) -> list[str]:
    """Resolve the tenant set to scan from CLI args (explicit list, file, or --all discovery)."""
    tenant_ids: list[str] = []
    if args.tenant:
        tenant_ids.extend(args.tenant)
    if args.tenants_file:
        with open(args.tenants_file, encoding="utf-8") as f:
            tenant_ids.extend(line.strip() for line in f if line.strip())
    if tenant_ids:
        # De-dup while preserving first-seen order.
        seen: set[str] = set()
        ordered = [t for t in tenant_ids if not (t in seen or seen.add(t))]
        return ordered
    # Default / --all: discover every tenant with a config#fields row via the operator scan.
    return _discover_tenants_with_config_fields(table=table)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "03a C6 HARD GATE: all-tenant scan confirming ZERO un-migrated bare-`choices` "
            "rows remain before C6 fail-loud is enabled. READ-ONLY. Exits non-zero (FAIL) if "
            "any bare-`choices` entry remains, zero (PASS) otherwise."
        )
    )
    parser.add_argument(
        "--tenant",
        action="append",
        default=[],
        help="Scan this tenant (repeatable). If omitted (and no --tenants-file), ALL tenants "
        "with a config#fields row are discovered and scanned.",
    )
    parser.add_argument(
        "--tenants-file",
        help="A file with one tenant_id per line to scan (combined with any --tenant values).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Explicitly scan ALL tenants (the default when no tenant list is given); discovers "
        "every tenant carrying a config#fields row via a one-shot read-only table scan.",
    )
    args = parser.parse_args(argv)

    reader = _build_reader()
    # Reuse the reader's already-resolved table handle for discovery so both share one client.
    tenant_ids = _resolve_tenant_ids(args, table=reader.table)
    if not tenant_ids:
        print("No tenants with a config#fields row found — nothing to scan (PASS).")
        return 0
    results = scan_tenants(tenant_ids, reader=reader)
    return _print_summary(results)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
