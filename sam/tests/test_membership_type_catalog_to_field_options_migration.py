"""
spec 03b Task 7.2 — unit tests for the membership_type EXPAND migration
(``sam/members/migration/membership_type_catalog_to_field_options.py``), the data half of design
"Migration" § EXPAND (Req 6.1a / 6.2).

Tested WITHOUT AWS / boto3 (steering 34/39): the whole file under test is split into a PURE
transform (fold + choices-strip + plan) and a thin gated boto3 runner. These tests exercise ONLY
the pure transform, over the COMMITTED REAL h-dcn fixture
``backend/tests/fixtures/hdcn_membership_type_integrity.json`` (the real-data basis, Task 7.1) —
not a hand-built abstraction. The last block proves the Task-7.1 integrity scan
(``scripts/scan_membership_type_integrity.py``) PASSES over the migration's transformed output —
the EXPAND→VERIFY contract.

**Validates: Requirements 6.1, 6.2** · **Property 1 (no orphaned reference), Property 2
(grandfather preserved)**
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.migration.membership_type_catalog_to_field_options import (  # noqa: E402
    DOTTED_MEMBERSHIP_TYPE_KEY,
    CatalogEntry,
    fold_catalog_into_options,
    merge_folded_options,
    plan_row_fold,
    row_needs_fold,
    strip_forbidden_choices,
)

_FIXTURES = os.path.join(_REPO_ROOT, "backend", "tests", "fixtures")


def _load_integrity_fixture() -> dict:
    with open(
        os.path.join(_FIXTURES, "hdcn_membership_type_integrity.json"), encoding="utf-8"
    ) as f:
        return json.load(f)


def _real_catalog() -> list[CatalogEntry]:
    """The 7 REAL h-dcn catalog rows (incl. erelid active:false) as the fold's input."""
    fx = _load_integrity_fixture()
    return [CatalogEntry.from_raw(r) for r in fx["catalog_rows"]]


# ── Load the Task-7.1 integrity scan module (scripts/ is not an importable package) ──────────
def _load_scan_module():
    path = os.path.join(_REPO_ROOT, "scripts", "scan_membership_type_integrity.py")
    spec = importlib.util.spec_from_file_location("scan_membership_type_integrity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1. fold_catalog_into_options — the core fold rule
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_fold_maps_each_catalog_entry_to_one_option_with_value_label_order_allowed():
    options = fold_catalog_into_options(_real_catalog())
    by_value = {o["value"]: o for o in options}

    # Every catalog code becomes an option value; nothing invented, nothing dropped.
    assert set(by_value) == {
        "gewoon_lid",
        "gezins_lid",
        "erelid",
        "donateur",
        "gezins_donateur",
        "sponsor",
        "overig",
    }
    # value = type_code, label carried through, order carried through.
    assert by_value["gewoon_lid"]["label"] == {"nl": "Gewoon lid", "en": "Regular member"}
    assert by_value["gewoon_lid"]["order"] == 10
    assert by_value["gewoon_lid"]["allowed"] is True


@pytest.mark.unit
def test_fold_retired_entry_folds_to_allowed_false_grandfathered():
    # erelid is the one retired catalog row (active:false) — it MUST fold to allowed:false.
    options = fold_catalog_into_options(_real_catalog())
    erelid = next(o for o in options if o["value"] == "erelid")
    assert erelid["allowed"] is False
    # every other h-dcn catalog entry is active -> allowed:true.
    assert all(o["allowed"] is True for o in options if o["value"] != "erelid")


@pytest.mark.unit
def test_fold_is_ordered_by_order_then_value_and_deterministic():
    options = fold_catalog_into_options(_real_catalog())
    orders = [o["order"] for o in options]
    assert orders == sorted(orders)
    # re-folding yields the identical list (idempotent/deterministic).
    assert fold_catalog_into_options(_real_catalog()) == options


@pytest.mark.unit
def test_fold_skips_blank_and_duplicate_type_codes():
    catalog = [
        CatalogEntry(type_code="  ", label={"nl": "blank"}, active=True, order=1),
        CatalogEntry(type_code="dup", label={"nl": "A"}, active=True, order=2),
        CatalogEntry(type_code="dup", label={"nl": "B"}, active=True, order=3),
    ]
    options = fold_catalog_into_options(catalog)
    assert [o["value"] for o in options] == ["dup"]


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2. strip_forbidden_choices — drop `choices` only where `options` co-exists
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_strip_removes_choices_when_options_coexist_including_region():
    overrides = {
        "demographics.region": {
            "type": "enum",
            "scope": {"enabled": True},
            "choices": ["Noord", "Zuid"],
            "options": [{"value": "noord"}, {"value": "zuid"}],
        },
    }
    cleaned, touched = strip_forbidden_choices(overrides)
    assert "choices" not in cleaned["demographics.region"]
    assert cleaned["demographics.region"]["options"] == [{"value": "noord"}, {"value": "zuid"}]
    assert touched == ["demographics.region"]


@pytest.mark.unit
def test_strip_leaves_choices_untouched_when_no_options_alongside():
    # A choices-only entry is NOT stripped — this migration never drops a sole vocabulary source.
    overrides = {"x.y": {"type": "enum", "choices": ["a", "b"]}}
    cleaned, touched = strip_forbidden_choices(overrides)
    assert cleaned["x.y"]["choices"] == ["a", "b"]
    assert touched == []


@pytest.mark.unit
def test_strip_is_pure_does_not_mutate_input():
    overrides = {"x.y": {"choices": ["a"], "options": [{"value": "a"}]}}
    strip_forbidden_choices(overrides)
    assert "choices" in overrides["x.y"]  # original untouched


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3. merge_folded_options — preserve admin-authored options with no catalog counterpart
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_merge_folded_is_source_of_truth_but_preserves_extra_authored_options():
    folded = [{"value": "a", "allowed": True}, {"value": "b", "allowed": False}]
    existing = [
        {"value": "a", "allowed": True, "stale": "ignored"},  # folded wins
        {"value": "custom", "label": {"nl": "Eigen"}},  # authored-only, preserved
    ]
    merged = merge_folded_options(existing, folded)
    by_value = {o["value"]: o for o in merged}
    assert set(by_value) == {"a", "b", "custom"}
    assert "stale" not in by_value["a"]  # folded replaced the authored `a`
    assert by_value["custom"]["label"] == {"nl": "Eigen"}


@pytest.mark.unit
def test_merge_with_no_existing_is_just_the_folded_list():
    folded = [{"value": "a", "allowed": True}]
    assert merge_folded_options(None, folded) == folded


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 4. row_needs_fold — idempotency detector
# ═══════════════════════════════════════════════════════════════════════════════════════════


def _folded_overrides() -> dict:
    """A membership_type override already fully folded from the real catalog (post-fold state)."""
    return {
        DOTTED_MEMBERSHIP_TYPE_KEY: {
            "type": "enum",
            "options": fold_catalog_into_options(_real_catalog()),
        }
    }


@pytest.mark.unit
def test_pre_fold_row_with_catalog_but_no_options_needs_fold():
    overrides = {DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True}}
    assert row_needs_fold(overrides, _real_catalog()) is True


@pytest.mark.unit
def test_fully_folded_row_is_idempotent_skip():
    assert row_needs_fold(_folded_overrides(), _real_catalog()) is False


@pytest.mark.unit
def test_row_with_forbidden_choices_beside_options_needs_fold():
    overrides = _folded_overrides()
    overrides["demographics.region"] = {"choices": ["x"], "options": [{"value": "x"}]}
    assert row_needs_fold(overrides, _real_catalog()) is True


@pytest.mark.unit
def test_row_missing_an_active_code_needs_fold():
    overrides = _folded_overrides()
    overrides[DOTTED_MEMBERSHIP_TYPE_KEY]["options"] = [
        o
        for o in overrides[DOTTED_MEMBERSHIP_TYPE_KEY]["options"]
        if o["value"] != "donateur"  # drop an active code
    ]
    assert row_needs_fold(overrides, _real_catalog()) is True


@pytest.mark.unit
def test_row_with_retired_code_still_allowed_true_needs_fold():
    overrides = _folded_overrides()
    for o in overrides[DOTTED_MEMBERSHIP_TYPE_KEY]["options"]:
        if o["value"] == "erelid":
            o["allowed"] = True  # retired but still offered -> must be re-folded to false
    assert row_needs_fold(overrides, _real_catalog()) is True


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 5. plan_row_fold — the end-to-end pure plan + idempotency
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_plan_folds_catalog_and_strips_region_choices_in_one_pass():
    overrides = {
        DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True},  # pre-fold: flags only
        "demographics.region": {
            "scope": {"enabled": True},
            "choices": ["Noord"],
            "options": [{"value": "noord"}],
        },
    }
    plan = plan_row_fold(overrides, _real_catalog(), "h-dcn")

    assert plan.changed is True
    # membership_type now carries the folded options, application flag preserved.
    mt = plan.new_overrides[DOTTED_MEMBERSHIP_TYPE_KEY]
    assert mt["application_visible"] is True
    assert {o["value"] for o in mt["options"]} == {
        "gewoon_lid", "gezins_lid", "erelid", "donateur",
        "gezins_donateur", "sponsor", "overig",
    }
    # region choices stripped, options kept.
    assert "choices" not in plan.new_overrides["demographics.region"]
    assert plan.new_overrides["demographics.region"]["options"] == [{"value": "noord"}]
    assert "demographics.region" in plan.choices_cleaned
    # the owner-verification listing includes erelid flagged retired.
    listed = dict(plan.option_values)
    assert listed["erelid"] is False
    assert listed["gewoon_lid"] is True


@pytest.mark.unit
def test_plan_on_already_folded_row_is_no_op():
    plan = plan_row_fold(_folded_overrides(), _real_catalog(), "h-dcn")
    assert plan.changed is False
    assert plan.new_overrides == {}
    # still LISTS the current option values for verification even on a skip.
    assert dict(plan.option_values)["erelid"] is False


@pytest.mark.unit
def test_plan_applied_twice_converges_second_pass_is_skip():
    overrides = {DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True}}
    first = plan_row_fold(overrides, _real_catalog(), "h-dcn")
    assert first.changed is True
    second = plan_row_fold(first.new_overrides, _real_catalog(), "h-dcn")
    assert second.changed is False  # re-running the fold is idempotent


@pytest.mark.unit
def test_plan_preserves_unrelated_override_attributes_verbatim():
    overrides = {
        DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True, "required": True},
        "personal.gender": {"type": "enum", "options": [{"value": "f"}]},
    }
    plan = plan_row_fold(overrides, _real_catalog(), "h-dcn")
    mt = plan.new_overrides[DOTTED_MEMBERSHIP_TYPE_KEY]
    assert mt["required"] is True and mt["application_visible"] is True
    # an unrelated field is untouched.
    assert plan.new_overrides["personal.gender"] == {"type": "enum", "options": [{"value": "f"}]}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 6. EXPAND → VERIFY: the Task-7.1 integrity scan PASSES over the transformed output
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_integrity_scan_passes_over_the_folded_output():
    # Fold the REAL catalog, then run the Task-7.1 pure integrity core over the resulting options +
    # the real member tally: zero un-folded active rows, zero orphaned references (incl. erelid).
    scan = _load_scan_module()
    fx = _load_integrity_fixture()

    plan = plan_row_fold(
        {DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True}},
        _real_catalog(),
        "h-dcn",
    )
    folded_entry = plan.new_overrides[DOTTED_MEMBERSHIP_TYPE_KEY]

    # Feed the migration's OWN output through the scan's extractor + core (the EXPAND->VERIFY gate).
    field_options = scan.extract_field_options({"overrides": {DOTTED_MEMBERSHIP_TYPE_KEY: folded_entry}})
    catalog_rows = [scan.CatalogRow.from_raw(r) for r in fx["catalog_rows"]]
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=dict(fx["member_tally"]),
    )
    assert result.clean, (
        "the migration's folded output must pass the Task-7.1 integrity scan: zero un-folded "
        "active catalog rows and zero orphaned member references"
    )
    assert result.unfolded_catalog_rows == ()
    assert result.orphaned_member_references == ()


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 7. run() composition root — the TWO-TABLE wiring (regression for the Task-7.3 bug)
# ═══════════════════════════════════════════════════════════════════════════════════════════
#
# The bug the live TEST dry-run surfaced: run() resolved ONE table (the projection table) and
# injected it into DynamoDbMembersRepository, so the catalog read (list_membership_types) queried
# the PROJECTION table — not the MEMBERS table where membershiptype# rows live — found ZERO catalog
# rows, and row_needs_fold returned False → the fold was SILENTLY SKIPPED for every tenant (the
# TEST run printed `SKIP h-dcn … options: []`).
#
# These tests inject TWO DISTINCT fakes — a projection fake holding a pre-fold config#fields row,
# and a members-repository fake holding the real membershiptype# catalog — and assert run() PLANS
# the fold (not SKIP) and LISTS the folded values with erelid retired. With the old one-table wiring
# (catalog read against an empty/wrong source) this would print SKIP and `options: []`, so the test
# would FAIL — which is exactly the gap that let the bug through.

import io  # noqa: E402

from sam.members.migration.membership_type_catalog_to_field_options import run  # noqa: E402
from sam.members.domain.membership_type_catalog import MembershipTypeEntry  # noqa: E402


class _FakeProjectionTable:
    """A stand-in for the PROJECTION table resource — the config#fields source.

    Only implements what run()'s scan path (`_scan_config_fields_rows`) and put path touch: a
    `scan` that returns the seeded config#fields row(s), a `name`, and a `put_item` capturing
    writes. It does NOT hold any membershiptype# catalog rows — proving the catalog must come from
    a SEPARATE source (the members repository), never from this table.
    """

    def __init__(self, items):
        self.name = "fake_governance_projection"
        self._items = list(items)
        self.put_items = []

    def scan(self, **kwargs):  # single page; the real filter is DynamoDB-side
        return {"Items": list(self._items)}

    def put_item(self, Item):
        self.put_items.append(Item)


class _FakeMembersRepository:
    """A stand-in for DynamoDbMembersRepository — the membershiptype# CATALOG source.

    Holds the catalog per tenant and serves it via `list_membership_types`, exactly as the real
    repository reads it from the MEMBERS table. run() must build the repository against the MEMBERS
    table and read the catalog from HERE — distinct from the projection table above.
    """

    def __init__(self, catalog_by_tenant):
        self._catalog_by_tenant = catalog_by_tenant
        self.queried_tenants = []

    def list_membership_types(self, tenant_id, *, active_only=False):
        self.queried_tenants.append(tenant_id)
        entries = self._catalog_by_tenant.get(tenant_id, [])
        if active_only:
            entries = [e for e in entries if e.active]
        return entries


def _real_catalog_entries(tenant_id: str) -> list[MembershipTypeEntry]:
    """The 7 REAL h-dcn catalog rows (incl. erelid active:false) as domain entries."""
    fx = _load_integrity_fixture()
    return [
        MembershipTypeEntry(
            tenant_id=tenant_id,
            type_code=str(r.get("type_code", "")),
            label=dict(r.get("label") or {}),
            active=bool(r.get("active", True)),
            order=int(r.get("order", 0) or 0),
        )
        for r in fx["catalog_rows"]
    ]


def _pre_fold_config_row(tenant_id: str) -> dict:
    """A pre-fold config#fields row: membership_type override carries flags but NO options.

    Mirrors the live TEST h-dcn override (attrs: application_visible, label, required, type, order,
    functional_group) — crucially, NO `options` key, so a correct fold must PLAN (not SKIP).
    """
    return {
        "tenant_id": tenant_id,
        "sk": "config#fields",
        "version": "v1",
        "overrides": {
            DOTTED_MEMBERSHIP_TYPE_KEY: {
                "application_visible": True,
                "functional_group": "membership",
                "label": {"nl": "Lidmaatschapstype"},
                "order": 10,
                "required": True,
                "type": "enum",
            },
        },
    }


@pytest.mark.unit
def test_run_dry_run_wires_catalog_from_members_repo_not_projection_table():
    # Two DISTINCT fakes: projection fake has the pre-fold row but NO catalog; the catalog lives
    # ONLY in the members-repository fake. If run() read the catalog from the projection table (the
    # bug), it would find zero rows and print SKIP / options: [].
    projection = _FakeProjectionTable([_pre_fold_config_row("h-dcn")])
    repo = _FakeMembersRepository({"h-dcn": _real_catalog_entries("h-dcn")})
    buf = io.StringIO()

    exit_code = run(
        [],  # no --apply: dry-run
        out=buf,
        projection_table=projection,
        members_repository=repo,
    )
    output = buf.getvalue()

    assert exit_code == 0
    # The catalog was read from the members repository, keyed by the config row's tenant.
    assert repo.queried_tenants == ["h-dcn"]
    # The fold is PLANNED, not silently skipped (the bug printed SKIP … options: []).
    assert "PLAN   h-dcn" in output
    assert "SKIP" not in output
    # The resulting option values are LISTED for owner verification, with erelid flagged retired.
    assert "erelid (retired)" in output
    for code in ("gewoon_lid", "gezins_lid", "donateur", "gezins_donateur", "sponsor", "overig"):
        assert code in output
    assert "options: []" not in output
    # Dry-run writes NOTHING.
    assert projection.put_items == []


@pytest.mark.unit
def test_run_apply_without_restore_point_refuses_to_write():
    # The two-flag write gate: --apply without --i-have-a-restore-point MUST refuse (exit 3) and
    # write nothing — the fix must not weaken this.
    projection = _FakeProjectionTable([_pre_fold_config_row("h-dcn")])
    repo = _FakeMembersRepository({"h-dcn": _real_catalog_entries("h-dcn")})
    buf = io.StringIO()

    exit_code = run(
        ["--apply"],  # missing --i-have-a-restore-point
        out=buf,
        projection_table=projection,
        members_repository=repo,
    )

    assert exit_code == 3
    assert projection.put_items == []
