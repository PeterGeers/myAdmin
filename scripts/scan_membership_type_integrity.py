#!/usr/bin/env python3
"""
03b BU-7 (Task 7.1) — the membership_type collapse INTEGRITY SCAN (the design proof, runnable).

This is the automated form of design.md's "Migration-safety proof" (Req 3.6) and the Req 6.3
pre/post-migration integrity scan: it asserts, per tenant and all-tenant, that the collapse of the
``membershiptype#<code>`` catalog into the ``membership_type`` field's enum ``options`` leaves

    (a) ZERO un-folded catalog rows   — every ACTIVE catalog ``type_code`` appears as a field
                                         option ``value`` (nothing the picker would still need lives
                                         only in the catalog); and
    (b) ZERO orphaned member references — every value stored in a member's
                                         ``membership.membership_type`` resolves to a field option,
                                         INCLUDING a grandfathered ``allowed:false`` option (e.g. the
                                         retired ``erelid`` the 4 h-dcn members still hold).

A retired option (``allowed:false``) is NOT an un-folded row and NOT an orphan: it is the design's
grandfather case — present as a field option (so references resolve) but not offered in the picker.
An ACTIVE catalog entry with zero members (e.g. ``sponsor``) must still appear as a field option
(it is an offered value); a members-held value that is NOT a field option at all is the orphan the
collapse must never create.

Relationship to the ``choices`` gate
-------------------------------------
This is the membership_type sibling of ``scripts/scan_config_fields_un_migrated_choices.py`` (03a's
C6 hard gate). Same shape: a PURE, storage-agnostic core (unit-tested over the committed REAL h-dcn
fixture ``backend/tests/fixtures/hdcn_membership_type_integrity.json``) plus a live, READ-ONLY
per-tenant driver and an all-tenant discovery mode, with an exit-code gate:

    exit 0  — PASS: across all scanned tenants, zero un-folded ACTIVE catalog rows AND zero orphaned
              member references. The fold is complete and orphan-free (the EXPAND/VERIFY gate, Req
              6.3); the catalog rows are safe to retire (CONTRACT, Task 10.1).
    exit 1  — FAIL (BLOCKING): at least one un-folded active catalog row OR one orphaned member
              reference remains — naming the tenant, the catalog code, or the member value. Re-run
              the EXPAND fold (Task 7.2 / scripts side) for the named tenant(s) until green.

Task 7.3 runs this on TEST (``test_*`` tables), Task 12 on PRODUCTION, each gating the next step
(account ``nonprofit-deploy`` / 506221081911 per steering 23/41). This script is READ-ONLY — it
NEVER writes a table.

Layering (steering 39)
----------------------
Like the ``choices`` scan + the migration scripts, this operator script is allowed to construct the
boto3-backed repository (the composition root ``app.py`` would otherwise provide) and, in ``--all``
mode, to run a one-shot read-only discovery ``scan`` of the projection table. The INTEGRITY CHECK
itself is the pure core (:func:`scan_membership_type`) over three resolved reads
(``get_raw_fields_overlay`` for the field options, ``list_membership_types`` for the catalog,
``list_members`` for the member tally) — no raw boto3 in the check.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# ── Path bootstrap (repo root + backend/src) so ``sam.*`` / ``services.*`` import when the
#    script is run directly, mirroring the sibling scan/migration scripts' bootstrap. ─────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

__all__ = [
    "DOTTED_MEMBERSHIP_TYPE_KEY",
    "FieldOption",
    "CatalogRow",
    "UnfoldedCatalogRow",
    "OrphanedMemberReference",
    "TenantIntegrityResult",
    "scan_membership_type",
    "scan_tenant",
    "scan_tenants",
    "main",
]

#: The dotted override key under which ``membership_type`` lives in the stored ``config#fields``
#: overrides map (``<group>.<key>`` — it is a fixed field in the ``membership`` storage bucket).
DOTTED_MEMBERSHIP_TYPE_KEY = "membership.membership_type"


# ── Normalised input shapes (what the pure core consumes) ─────────────────────────────────────


@dataclass(frozen=True)
class FieldOption:
    """One resolved ``membership_type`` field option (the post-fold vocabulary).

    ``allowed`` defaults to ``True`` so an option authored before the 03b flag (absent ``allowed``)
    reads as offered — the same back-compat default as :class:`sam.members.domain.fixed_fields.EnumOption`.
    An ``allowed:false`` option is a RETIRED/grandfathered value: it still RESOLVES a member
    reference (so it is never an orphan) but is not offered in the picker.
    """

    value: str
    allowed: bool = True

    @classmethod
    def from_raw(cls, raw: Mapping) -> "FieldOption":
        return cls(value=str(raw.get("value")), allowed=bool(raw.get("allowed", True)))


@dataclass(frozen=True)
class CatalogRow:
    """One ``membershiptype#<code>`` catalog row at fold time (the shape being folded away)."""

    type_code: str
    active: bool = True

    @classmethod
    def from_raw(cls, raw: Mapping) -> "CatalogRow":
        return cls(type_code=str(raw.get("type_code")), active=bool(raw.get("active", True)))


# ── Offender shapes ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnfoldedCatalogRow:
    """An ACTIVE catalog ``type_code`` that is NOT present as a field option (fold incomplete)."""

    tenant_id: str
    type_code: str


@dataclass(frozen=True)
class OrphanedMemberReference:
    """A stored member ``membership.membership_type`` value that resolves to NO field option.

    ``member_count`` is how many members hold the orphaned value (from the tally) so the report
    conveys blast radius, not just the bare value.
    """

    tenant_id: str
    value: str
    member_count: int


@dataclass(frozen=True)
class TenantIntegrityResult:
    """The outcome of scanning ONE tenant's membership_type collapse integrity."""

    tenant_id: str
    unfolded_catalog_rows: tuple[UnfoldedCatalogRow, ...] = field(default_factory=tuple)
    orphaned_member_references: tuple[OrphanedMemberReference, ...] = field(
        default_factory=tuple
    )

    @property
    def clean(self) -> bool:
        return not self.unfolded_catalog_rows and not self.orphaned_member_references


# ── Pure scan core (no boto3 — unit-testable in isolation over the resolved slices) ────────────


def scan_membership_type(
    tenant_id: str,
    *,
    field_options: Sequence[FieldOption],
    catalog_rows: Sequence[CatalogRow],
    member_tally: Mapping[str, int],
) -> TenantIntegrityResult:
    """Enumerate the collapse-integrity offenders for ONE tenant (pure, the design proof).

    - ``field_options`` — the resolved ``membership_type`` field option list (post-fold vocabulary).
    - ``catalog_rows`` — the tenant's ``membershiptype#<code>`` catalog rows (active + retired).
    - ``member_tally`` — ``{stored membership_type value: member count}`` over the FULL population.

    Returns a :class:`TenantIntegrityResult`. Two independent checks:

    (a) **Zero un-folded catalog rows.** Every ACTIVE catalog ``type_code`` must appear as a field
        option ``value``. A retired (``active=False``) catalog row is NOT required as an offered
        option — it may be folded to ``allowed:false`` or legitimately absent — so it is never an
        un-folded offender. An active code missing from the options is an un-folded row.
    (b) **Zero orphaned member references.** Every value in ``member_tally`` must resolve to SOME
        field option — allowed OR ``allowed:false`` (the grandfather case resolves, it is not an
        orphan). A member-held value present in NO option is an orphan.
    """
    option_values = {o.value for o in field_options}  # allowed + retired both resolve references

    unfolded = tuple(
        UnfoldedCatalogRow(tenant_id=tenant_id, type_code=row.type_code)
        for row in catalog_rows
        if row.active and row.type_code not in option_values
    )

    orphans = tuple(
        OrphanedMemberReference(
            tenant_id=tenant_id, value=value, member_count=int(count)
        )
        for value, count in member_tally.items()
        if value not in option_values
    )

    return TenantIntegrityResult(
        tenant_id=tenant_id,
        unfolded_catalog_rows=unfolded,
        orphaned_member_references=orphans,
    )


# ── Resolved-read extractors (turn the repository's resolved views into the core's inputs) ─────


def extract_field_options(overlay_wire: Mapping) -> list[FieldOption]:
    """Pull the ``membership_type`` field options out of the resolved ``config#fields`` wire shape.

    ``overlay_wire`` is what ``get_raw_fields_overlay`` returns (``fields`` + ``fixed_overrides``).
    ``membership_type`` is a FIXED field, so its authored options live in the ``fixed_overrides``
    map under the dotted key ``membership.membership_type``. A pre-fold row with no inline options
    yields an empty list (every active catalog row then reports un-folded — correct: the fold has
    not run yet).
    """
    overrides = overlay_wire.get("fixed_overrides") or overlay_wire.get("overrides") or {}
    entry = overrides.get(DOTTED_MEMBERSHIP_TYPE_KEY) or {}
    raw_options = entry.get("options") or ()
    return [FieldOption.from_raw(o) for o in raw_options if isinstance(o, Mapping)]


def tally_member_types(members: Sequence[Mapping]) -> dict[str, int]:
    """Count stored member records by ``membership.membership_type`` (ignoring absent values).

    A member record is the raw dict the repository's ``list_members`` returns; the type lives at
    ``member["membership"]["membership_type"]``. A member with no membership_type set is skipped
    (not an orphan — it holds no reference to resolve).
    """
    tally: dict[str, int] = {}
    for member in members:
        membership = member.get("membership") if isinstance(member, Mapping) else None
        value = membership.get("membership_type") if isinstance(membership, Mapping) else None
        if value is None or value == "":
            continue
        tally[value] = tally.get(value, 0) + 1
    return tally


# ── The live driver (reads each tenant's resolved views; runs the pure check; reports) ─────────


def scan_tenant(tenant_id: str, *, reader, repository) -> TenantIntegrityResult:
    """Read one tenant's three resolved slices and run the pure integrity check (READ-ONLY).

    - ``reader`` exposes ``get_raw_fields_overlay(tenant_id, *, consistent_read=True)`` — the
      resolved ``config#fields`` wire shape (strongly consistent so a just-run fold is reflected;
      the gate must not pass on a stale view).
    - ``repository`` exposes ``list_membership_types(tenant_id, active_only=...)`` and
      ``list_members(tenant_id)`` — the catalog rows and the member population to tally.
    """
    overlay_wire = reader.get_raw_fields_overlay(tenant_id, consistent_read=True)
    field_options = extract_field_options(overlay_wire)

    catalog_rows = [
        CatalogRow(type_code=e.type_code, active=bool(e.active))
        for e in repository.list_membership_types(tenant_id)
    ]
    member_tally = tally_member_types(repository.list_members(tenant_id))

    return scan_membership_type(
        tenant_id,
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )


def scan_tenants(
    tenant_ids: Sequence[str], *, reader, repository, out=None
) -> list[TenantIntegrityResult]:
    """Scan EVERY tenant in ``tenant_ids`` and print a per-tenant/per-offender report.

    Returns one :class:`TenantIntegrityResult` per tenant so a caller / test can assert the
    outcome. The printed report names every un-folded catalog code and every orphaned member value
    so an operator can act on exactly those tenants.
    """
    out = out if out is not None else sys.stdout
    results: list[TenantIntegrityResult] = []
    for tenant_id in tenant_ids:
        result = scan_tenant(tenant_id, reader=reader, repository=repository)
        results.append(result)
        if result.clean:
            print(
                f"[{tenant_id}] OK — every active catalog type is a field option and every "
                f"member reference resolves.",
                file=out,
            )
        else:
            for off in result.unfolded_catalog_rows:
                print(
                    f"[{tenant_id}] UN-FOLDED: catalog type {off.type_code!r} is active but is "
                    f"NOT a membership_type field option (the fold is incomplete).",
                    file=out,
                )
            for orphan in result.orphaned_member_references:
                print(
                    f"[{tenant_id}] ORPHAN: {orphan.member_count} member(s) hold "
                    f"membership_type {orphan.value!r} which resolves to NO field option.",
                    file=out,
                )
    return results


def _print_summary(results: Sequence[TenantIntegrityResult], *, out=None) -> int:
    """Print the gate verdict and return the process exit code (0 PASS / 1 FAIL)."""
    out = out if out is not None else sys.stdout
    total_unfolded = sum(len(r.unfolded_catalog_rows) for r in results)
    total_orphans = sum(len(r.orphaned_member_references) for r in results)
    offender_tenants = [r.tenant_id for r in results if not r.clean]
    scanned = len(results)
    if total_unfolded == 0 and total_orphans == 0:
        print(
            f"\nPASS — scanned {scanned} tenant(s); ZERO un-folded active catalog rows and ZERO "
            f"orphaned member references. The membership_type fold is complete and orphan-free.",
            file=out,
        )
        return 0
    print(
        f"\nFAIL (BLOCKING) — scanned {scanned} tenant(s); found {total_unfolded} un-folded active "
        f"catalog row(s) and {total_orphans} orphaned member reference(s) across "
        f"{len(offender_tenants)} tenant(s): {', '.join(offender_tenants)}.\n"
        f"Re-run the EXPAND fold for those tenant(s), then re-run this scan. The catalog rows MUST "
        f"NOT be retired until this gate is green.",
        file=out,
    )
    return 1


# ── Composition root + tenant discovery (operator-level; NOT the repository layer) ─────────────


def _build_reader_and_repository(table=None):
    """Compose the boto3-backed resolved reader + members repository for a live run.

    This is what ``app.py`` would otherwise provide. The table resolves fail-fast from the
    governance/members table env var inside each; a ``table`` may be injected (tests / a
    local-DynamoDB run).
    """
    from sam.members.repository.members_repository import DynamoDbMembersRepository
    from sam.members.repository.projection_config_reader import MembersProjectionReader

    reader = MembersProjectionReader(table=table)
    repository = DynamoDbMembersRepository(table=table)
    return reader, repository


def _discover_tenants_with_config_fields(table=None) -> list[str]:
    """Operator-level ONE-SHOT, READ-ONLY discovery of tenants carrying a ``config#fields`` row.

    Mirrors the ``choices`` scan's discovery: a projection-table ``scan`` HERE in the operator
    script's composition root — NOT in the repository layer — to enumerate which ``tenant_id``
    partitions have a ``config#fields`` sort key. The offender check still goes through the
    per-tenant resolved reads, so the repository's "no cross-tenant scan" rule is intact. Returns a
    sorted, de-duplicated list of ``tenant_id``, paginating the scan so a large table is covered.
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
        seen: set[str] = set()
        return [t for t in tenant_ids if not (t in seen or seen.add(t))]
    return _discover_tenants_with_config_fields(table=table)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "03b membership_type collapse integrity scan: per-tenant / all-tenant assertion that "
            "zero active catalog rows are un-folded and zero member references are orphaned. "
            "READ-ONLY. Exits non-zero (FAIL) if any offender remains, zero (PASS) otherwise."
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

    reader, repository = _build_reader_and_repository()
    tenant_ids = _resolve_tenant_ids(args, table=reader.table)
    if not tenant_ids:
        print("No tenants with a config#fields row found — nothing to scan (PASS).")
        return 0
    results = scan_tenants(tenant_ids, reader=reader, repository=repository)
    return _print_summary(results)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
