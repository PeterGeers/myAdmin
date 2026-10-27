"""
TRUNCATION TRIPWIRE — the occurrence-3 proof test, PROVEN GREEN by Phase 2 (spec 03, Phase 1 task
1.3 → Phase 2 task 2.8; design C5; R9).

================================================================================================
WHAT CHANGED AT TASK 2.8 (read before touching a case)
================================================================================================
Phase 1 (task 1.3) authored these tripwires RED against the OLD whole-row ``put_config`` write
path and marked them ``xfail(strict=True)``: a partial ``functional_groups`` payload REPLACED the
whole catalog, so the catalog truncated 6 → 1 and every field in a dropped group was orphaned —
RED was the Phase-1 SUCCESS condition (the proof the occurrence-3 bug exists), and the strict
marker was a tripwire on its OWN removal ("when this starts to PASS, Phase 2 has landed — remove
the xfail").

Phase 2 has landed. Task 2.8 RE-POINTS these tripwires at the NEW Change-Op write path
(:class:`_ChangeOpGroupWriter` below — ``ConfigFieldsCrudService.set_group`` →
``MembersConfigWriteRepository.apply_ops`` single version-conditional ``update_item``) and the
``xfail`` markers are REMOVED. They are now LIVE GREEN acceptance-gate cases: a regression that
re-introduces a whole-catalog write reddens CI (R11.3). The occurrence-3 invariant is asserted
positively — a partial group edit changes ONLY that group; the catalog does NOT shrink and no
field is orphaned.

What occurrence 3 was (``.kiro/specs/Members/root-cause-analysis.md`` §"THE PARTIAL-OVERLAY-
OVERWRITES-FULL-RECORD BUG"): a group edit+save on TEST (2026-10-26) rewrote ``functional_groups``
from 6 → 2. The client's working overlay was a PARTIAL delta; the whole-row write dropped every
group/field absent from the partial payload. This file reproduces that exact EDIT (change one
group's order/label) against the REAL seeded ``h-dcn`` row and proves — via the invariant engine
(task 1.2) — that under the Change-Op path a partial slice can NO LONGER reduce the catalog /
orphan a field. Because an ``update_item`` only ever writes the attributes the ops name, the
guarantee is STRUCTURAL (in the verb), not "safe if a merge is flawless" (design D2).

Two tripwires (design C5 "Truncation tripwire", R9.2) — both the GROUPS catalog count and the
field grouping it governs, since the catalog truncation is what stripped the fields' sections:
  1. a partial GROUPS edit MUST NOT reduce the ``functional_groups`` catalog count;
  2. that same partial GROUPS edit MUST NOT reduce the field count OR orphan any field from its
     resolved group (the "most groups say they have no fields" symptom of occurrence 3).

Reusability (R9.4): the proof is driven through the generic engine
(:func:`assert_change_op_isolated`) over a resolved-record adapter, so the same tripwire shape is
reusable for ``config#scope`` / ``config#mail`` / member CRUD.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.config_fields_crud_service import (  # noqa: E402
    ConfigFieldsCrudService,
)
from sam.members.domain.field_resolver import FieldResolver  # noqa: E402
from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    MembersConfigWriteRepository,
)

from .invariant import ChangeOp, assert_change_op_isolated  # noqa: E402

# Container-gated e2e: skips cleanly without the local-DynamoDB container (via the
# seeded_config_fields_table → local_dynamodb_endpoint fixture chain, task 1.1).
pytestmark = pytest.mark.e2e


# ─────────────────────────────────────────────────────────────────────────────────────
# Resolved-record adapter + Change-Op (group) writer over the LIVE seeded h-dcn row
# ─────────────────────────────────────────────────────────────────────────────────────
def _resolved_record(table, tenant_id: str) -> dict:
    """Read the FULL Resolved_Record as an identity-keyed tree the invariant engine diffs.

    Shape matches the engine's ``ChangeOp`` path conventions (``functional_groups.<gkey>.<attr>``
    and ``fields.<key>.<attr>``): the catalog keyed by group key, the fields keyed by bare field
    key — each carrying the resolved attributes a consumer actually sees (steering 39: the raw
    stored shape never crosses the boundary; the invariant is proven on the resolved view).

    A FRESH :class:`MembersProjectionReader` is built per call ON PURPOSE: the reader keeps a
    per-instance partition cache, so reusing ONE reader for the before- and after-read would serve
    the cached pre-write state as the "after" and HIDE the very truncation this tripwire must
    observe. The before/after reads each get their own reader so each sees the live stored row.
    """
    config = FieldResolver(MembersProjectionReader(table=table)).resolve(tenant_id)
    return {
        "functional_groups": {
            g.key: {"label": dict(g.label), "order": g.order}
            for g in config.functional_groups
        },
        "fields": {
            f.key: {
                "functional_group": f.functional_group,
                "label": dict(f.label) if f.label else {},
                "order": f.order,
            }
            for f in config.fields
        },
    }


class _ChangeOpGroupWriter:
    """Drives the NEW (non-truncating) Change-Op group write path — the thing now PROVEN.

    Wires the REAL :class:`ConfigFieldsCrudService` to the REAL
    :class:`MembersConfigWriteRepository` (its ``apply_ops`` single version-conditional
    ``update_item``) over the live table, plus a reader for the service's strongly-consistent
    validate-and-place read. ``edit_one_group`` applies the SAME single-group edit that truncated
    the catalog on the old path — but as ONE identity-keyed ``set_group`` op addressing ONLY
    ``functional_groups.<gkey>``, so DynamoDB leaves every other group physically untouched.

    A FRESH reader + repository are built per edit (like :func:`_resolved_record`) so the service's
    placement/version read sees live DynamoDB state, not a cached pre-write partition.
    """

    def __init__(self, table, tenant_id: str):
        self._table = table
        self._tenant_id = tenant_id

    def _service(self) -> ConfigFieldsCrudService:
        reader = MembersProjectionReader(table=self._table)
        repository = MembersConfigWriteRepository(
            table=self._table, version_fn=_monotonic_version
        )
        return ConfigFieldsCrudService(repository, reader=reader)

    def edit_one_group(self, group_key: str, *, order: int, label: dict) -> None:
        """Edit ONE existing group's order + label — exactly the partial group-modal edit that
        truncated the catalog 6 → 2 on TEST, now routed through the Change-Op path."""
        self._service().set_group(
            self._tenant_id, group_key, {"order": order, "label": label}
        )


_version_counter = 0


def _monotonic_version() -> str:
    """A strictly-increasing version stamp so repeated writes in one test never collide."""
    global _version_counter
    _version_counter += 1
    return f"v-tripwire-{_version_counter:06d}"


# ─────────────────────────────────────────────────────────────────────────────────────
# Tripwire 1 — a partial GROUPS edit MUST NOT reduce the catalog count
# ─────────────────────────────────────────────────────────────────────────────────────
def test_partial_groups_save_must_not_truncate_catalog(seeded_config_fields_table):
    """A group edit that touches ONE group MUST leave every other group intact (occurrence 3).

    GREEN under Phase 2: ``set_group`` addresses ONLY ``functional_groups.personal`` via a single
    ``update_item``, so the catalog is unchanged except for that group's order/label. The old
    whole-row ``put_config`` replaced the catalog with the one-entry payload and dropped the rest
    (the RED proof); the Change-Op path cannot.
    """
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]

    writer = _ChangeOpGroupWriter(table, tenant_id)

    before = _resolved_record(table, tenant_id)
    catalog_before = set(before["functional_groups"])
    assert len(catalog_before) >= 2, (
        "fixture sanity: the real h-dcn catalog must have several groups to prove truncation"
    )
    assert "personal" in catalog_before, "fixture sanity: 'personal' must be a catalog group"

    # Edit ONE existing group (change its order + label) — the partial group-modal edit that
    # truncated the catalog 6 → 2 on TEST. Through the Change-Op path this touches only `personal`.
    writer.edit_one_group(
        "personal",
        order=11,
        label={"nl": "Persoonlijk", "en": "Personal"},
    )

    after = _resolved_record(table, tenant_id)
    catalog_after = set(after["functional_groups"])

    # The occurrence-3 invariant: a partial edit must NOT drop any group (R9.2 / design C5).
    dropped = catalog_before - catalog_after
    assert not dropped, (
        f"TRUNCATION regression: a partial groups edit dropped {sorted(dropped)} from the catalog "
        f"({len(catalog_before)} -> {len(catalog_after)}). This is occurrence 3 — the Change-Op "
        f"path must never write the whole catalog."
    )
    # Completeness the other direction: the edit introduced no spurious group either.
    assert catalog_before == catalog_after, (
        f"the catalog key set must be byte-stable across a single-group edit; "
        f"before={sorted(catalog_before)} after={sorted(catalog_after)}"
    )

    # And prove it through the generic engine: the op named ONLY personal.order + personal.label;
    # any other changed path (a vanished group) is a leak the engine names precisely.
    op = ChangeOp.set_group("personal", "order", "label")
    assert_change_op_isolated(before, op, after)

    # The edit DID take effect (completeness, not just isolation): personal.order changed to 11.
    assert after["functional_groups"]["personal"]["order"] == 11, (
        "the single-group edit must actually persist the new order (the write is real, not a no-op)"
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# Tripwire 2 — a partial GROUPS edit MUST NOT orphan fields / reduce their grouping
# ─────────────────────────────────────────────────────────────────────────────────────
#
# WHY THIS SHAPE (verified against current code at Phase 1, not inferred): the task's second clause
# is "a partial fields payload MUST NOT reduce the field count". The per-key field/override MERGE
# already preserved every field a partial `fields` body omits even on the OLD path — so an
# independent "partial fields save drops a field" never reproduced. The GENUINE field-side damage
# from occurrence 3 is not a field-count drop but FIELD ORPHANING: when the partial GROUPS save
# truncated the catalog (tripwire 1), every field whose `functional_group` pointed at a now-vanished
# group was orphaned — the "most groups say they have no fields, labels gone" symptom in
# `root-cause-analysis.md`/`findings.md`. Tripwire 2 asserts the field-grouping invariant (no field
# orphaned, every field's resolved group stays in the catalog) over the SAME partial-groups edit.
# RED on the old path; GREEN under Phase 2's per-path write, which never truncates the catalog and
# so never orphans a field.
def test_partial_groups_save_must_not_orphan_fields(seeded_config_fields_table):
    """A partial groups edit MUST NOT strip any field's resolved group (no orphaning).

    GREEN under Phase 2: the Change-Op ``set_group`` never truncates the catalog, so no field is
    left pointing at a group no longer present. On the old whole-row path the catalog truncation
    orphaned every field of a dropped group — the RED proof this now replaces.
    """
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]

    writer = _ChangeOpGroupWriter(table, tenant_id)

    before = _resolved_record(table, tenant_id)
    groups_before = {g for f in before["fields"].values() if (g := f["functional_group"])}
    assert len(before["functional_groups"]) >= 2, "fixture sanity: need several groups"

    # The SAME partial group-modal edit as tripwire 1 (edit one group, touch only it).
    writer.edit_one_group(
        "personal",
        order=11,
        label={"nl": "Persoonlijk", "en": "Personal"},
    )

    after = _resolved_record(table, tenant_id)
    catalog_after = set(after["functional_groups"])

    # 1) field COUNT must not shrink (the literal task clause — pinned so a future regression that
    #    DOES drop field entries is also caught).
    dropped_fields = set(before["fields"]) - set(after["fields"])
    assert not dropped_fields, (
        f"a partial groups edit dropped field entries {sorted(dropped_fields)} "
        f"({len(before['fields'])} -> {len(after['fields'])})"
    )

    # 2) the edit must not NEWLY orphan any field. We compare BEFORE↔AFTER rather than asserting
    #    absolute orphan-freeness: the real resolved h-dcn row ALREADY resolves several base fields
    #    (motor/financial/… groups) outside the live catalog set — a pre-existing resolver/catalog
    #    condition (see the known `test_resolved_base_fields_are_never_orphaned_into_an_other_group`
    #    in `test_field_config_realdata_roundtrip.py`), NOT a product of this write. Occurrence 3's
    #    damage is a NEW orphaning CAUSED by a catalog truncation, so the invariant that detects it
    #    is "no field that was correctly grouped before is orphaned after". A field is "correctly
    #    grouped" when its resolved group is in the catalog.
    def _orphans(record: dict, catalog: set) -> set:
        return {
            key
            for key, spec in record["fields"].items()
            if spec["functional_group"] and spec["functional_group"] not in catalog
        }

    orphans_before = _orphans(before, set(before["functional_groups"]))
    orphans_after = _orphans(after, catalog_after)
    newly_orphaned = sorted(orphans_after - orphans_before)
    assert not newly_orphaned, (
        f"ORPHANED regression: a partial groups edit NEWLY orphaned {len(newly_orphaned)} "
        f"field(s) — their resolved group vanished from the catalog {sorted(catalog_after)}: "
        f"{newly_orphaned}. The catalog truncation (occurrence 3) stripped their section ('most "
        f"groups say they have no fields'). (pre-existing orphans, not caused by this write: "
        f"{sorted(orphans_before)})"
    )

    # 3) every catalog group a CORRECTLY-GROUPED field referenced before is STILL in the catalog —
    #    the grouping those fields depend on survived the edit in full (the field-section half of
    #    occurrence 3). Groups that were already outside the catalog before are excluded (they are
    #    the pre-existing condition, not this write's doing).
    referenced_in_catalog_before = {
        g for g in groups_before if g in before["functional_groups"]
    }
    missing_referenced = sorted(referenced_in_catalog_before - catalog_after)
    assert not missing_referenced, (
        f"a partial groups edit dropped group(s) {missing_referenced} that correctly-grouped "
        f"fields still reference — the field-section truncation half of occurrence 3"
    )
