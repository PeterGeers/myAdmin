"""TransformedRow, [PERSON_NAME] and build_backfill_plan.

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .source_layout import HDCN_TENANT_ID, RegionCanonicalizer
from .sources import HdcnSourceAdapter
from .transform import map_hdcn_row
from .vocabulary import (
    _REGION_FIELD_KEY,
    MembershipTypeMapper,
    RowSkipped,
    RowTransformError,
)


@dataclass(frozen=True)
class TransformedRow:
    """One successfully transformed source row: the produced member record + a back-reference."""

    member_id: str
    member_number: str
    member_type_code: str
    region: tuple[str, ...]
    record: Mapping[str, Any]


@dataclass
class BackfillPlan:
    """The result of transforming a source, ready to render (dry-run) or apply.

    A **fidelity check** of the transform against the source: counts, the per-field mapping
    summary, per-row validation errors, sample transformed records, and the member numbers
    that would collide within the batch. In dry-run the runner renders this and writes
    NOTHING; only with ``--apply`` does it persist :attr:`transformed` via the repository.
    """

    tenant_id: str
    source_description: str
    source_row_count: int = 0
    transformed: list[TransformedRow] = field(default_factory=list)
    #: (member_ref, {dotted_key: reason}) for rows that failed to map — surfaced, never dropped.
    errors: list[tuple[str, Mapping[str, str]]] = field(default_factory=list)
    #: (label, reason) for rows intentionally SKIPPED (counted as "skipped (empty)", DISTINCT
    #: from errors — never transformed/written). s5m follow-up: an R7.2 EMPTY row (incl. a
    #: placeholder-only row) and a Donateur-coded ``Lidnummer`` row both land here (see RowSkipped).
    skipped: list[tuple[str, str]] = field(default_factory=list)
    #: non-empty member numbers appearing on more than one row in this batch — a DATA-QUALITY
    #: warning only (reported; NOT skipped or blocked — the uniqueness guard was removed in s5k).
    duplicate_member_numbers: dict[str, list[str]] = field(default_factory=dict)
    #: rows whose region did not resolve to a scope value (reported, not fatal).
    rows_missing_region: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.transformed)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def field_mapping_summary(self) -> dict[str, int]:
        """Count, across successful rows, how many carry each fixed dotted field + overlay keys.

        A quick fidelity signal: it shows the mapping actually populated the expected fields
        (e.g. every row has ``membership.member_number``) and how widely overlay/club fields
        appear.
        """
        counts: dict[str, int] = {}
        for t in self.transformed:
            rec = t.record
            for group in ("personal", "membership"):
                for key in rec.get(group) or {}:
                    counts[f"{group}.{key}"] = counts.get(f"{group}.{key}", 0) + 1
            # S5d D1: the scope field (region) is a plain `overlay.region` field now — it is
            # counted by the overlay loop below (no separate `scope_values.region` count).
            for key in rec.get("overlay") or {}:
                counts[f"overlay.{key}"] = counts.get(f"overlay.{key}", 0) + 1
        return counts


def build_backfill_plan(
    adapter: HdcnSourceAdapter,
    *,
    type_mapper: MembershipTypeMapper | None = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: RegionCanonicalizer | None = None,
) -> BackfillPlan:
    """Read the source (read-only) + transform every row into a :class:`BackfillPlan`.

    Non-destructive: it only iterates the adapter's ``rows()`` (a read) and builds an in-memory
    plan — it never writes anything. Rows that fail to map are collected into
    :attr:`BackfillPlan.errors` (the dry-run reports them; the batch is not aborted). s5k: EVERY
    transformable row is imported — a numberless row is a valid member (empty ``member_number``)
    and a reused number is a DATA-QUALITY warning recorded in
    :attr:`BackfillPlan.duplicate_member_numbers` (reported, never skipped or overwritten — the
    ``membernum#`` uniqueness guard was removed).
    """
    plan = BackfillPlan(tenant_id=tenant_id, source_description=adapter.describe())

    # PASS 1: transform every row into a candidate; collect member-numbers so duplicates can
    # be identified across the WHOLE batch (not just "already seen so far"). Skips/errors are
    # recorded here; the region-missing tally is deferred to pass 2 (only kept rows count).
    candidates: list[TransformedRow] = []
    number_owners: dict[str, list[str]] = {}

    for raw in adapter.rows():
        plan.source_row_count += 1
        try:
            record = map_hdcn_row(
                raw,
                type_mapper=type_mapper,
                tenant_id=tenant_id,
                region_canonicalizer=region_canonicalizer,
            )
        except RowSkipped as exc:
            plan.skipped.append((exc.label, exc.reason))
            continue
        except RowTransformError as exc:
            plan.errors.append((exc.member_ref, exc.reasons))
            continue

        number = record["membership"].get("member_number", "")
        region_value = record.get("overlay", {}).get(_REGION_FIELD_KEY)
        candidates.append(
            TransformedRow(
                member_id=record["member_id"],
                member_number=number,
                member_type_code=record["membership"]["membership_type"],
                region=(region_value,) if region_value else (),
                record=record,
            )
        )
        # Group ONLY by a non-empty number: an empty `member_number` (numberless sponsor/club)
        # is not a "reused number" and must never be lumped into a duplicate bucket.
        if number:
            number_owners.setdefault(number, []).append(record["member_id"])

    plan.duplicate_member_numbers = {
        number: ids for number, ids in number_owners.items() if len(ids) > 1
    }

    # PASS 2: s5k — IMPORT EVERY ROW, including reused numbers. The `membernum#` uniqueness guard
    # is gone: a member number reused in the source is a DATA-QUALITY warning, not a write-time
    # conflict, so it no longer justifies dropping real members. `duplicate_member_numbers` is
    # still computed and REPORTED (the fidelity report lists it) so the data owner can reconcile a
    # recycled/duplicated Lidnummer in the source — but nothing is skipped for it.
    for cand in candidates:
        plan.transformed.append(cand)
        if not cand.region:
            plan.rows_missing_region.append(cand.member_id)

    return plan
