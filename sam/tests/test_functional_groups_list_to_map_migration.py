"""
spec 03 Task 2.0 — unit tests for the `functional_groups` LIST→MAP migration + dual-read
(design C6 / D2a, design-review Q3a/Q11, external-review Must-fix #4).

Two layers, both PURE (no boto3 / no AWS — the migration's dangerous whole-row `put_item` is gated
behind two explicit CLI flags and is NOT exercised here; only the transform/plan and the
reader/resolver round-trip are):

1. The migration transform (`convert_functional_groups` / `needs_migration` / `plan_row_migration`):
   LIST→MAP conversion, idempotency, skeleton + version backfill, every OTHER attribute preserved.

2. The **migration INVARIANT** (design C5 / R9, review harness-gap LIST→MAP case): a row MIGRATED by
   this transform and the ALREADY-MAP real fixture resolve to the IDENTICAL resolved field config —
   the migration changes the storage SHAPE, never the resolved view a consumer sees. Proven against
   the REAL h-dcn row (`steering 39`: trust runs, not inference) in BOTH shapes.
"""

from __future__ import annotations

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

from services import projection_schema as schema

from sam.members.domain.field_resolver import FieldResolver
from sam.members.migration.functional_groups_list_to_map import (
    convert_functional_groups,
    needs_migration,
    plan_row_migration,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
_MAP_FIXTURE = os.path.join(_FIXTURES, "hdcn_config_fields_overlay.json")
_LIST_FIXTURE = os.path.join(_FIXTURES, "hdcn_config_fields_overlay_legacy_groups_list.json")


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FakeTable:
    """In-memory DynamoDB Table stand-in (query side) — mirrors the sibling reader tests."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = dict(item)

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


# ── 1. the pure transform ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_convert_list_to_map_rekeys_by_group_key():
    raw = [
        {"key": "personal", "label": {"en": "Personal"}, "order": 1},
        {"key": "motor", "label": {"en": "Motor"}, "order": 2},
    ]
    out = convert_functional_groups(raw)
    assert out == {
        "personal": {"key": "personal", "label": {"en": "Personal"}, "order": 1},
        "motor": {"key": "motor", "label": {"en": "Motor"}, "order": 2},
    }


@pytest.mark.unit
def test_convert_is_idempotent_on_an_already_map_row():
    already_map = {
        "personal": {"key": "personal", "label": {"en": "Personal"}, "order": 1},
    }
    assert convert_functional_groups(convert_functional_groups(already_map)) == already_map


@pytest.mark.unit
def test_convert_fills_in_key_from_map_key_when_entry_omits_it():
    out = convert_functional_groups({"motor": {"label": {"en": "Motor"}, "order": 2}})
    assert out["motor"]["key"] == "motor"


@pytest.mark.unit
def test_convert_drops_keyless_or_nonmapping_list_entries():
    raw = [{"label": {"en": "no key"}}, "not-a-dict", {"key": "ok", "order": 1}]
    assert convert_functional_groups(raw) == {"ok": {"key": "ok", "order": 1}}


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, 0, "x", 3.14])
def test_convert_non_catalog_input_is_empty_map(raw):
    assert convert_functional_groups(raw) == {}


@pytest.mark.unit
def test_needs_migration_true_for_legacy_list_row():
    row = {"fields": {}, "overrides": {}, "functional_groups": [], "version": 1}
    assert needs_migration(row) is True


@pytest.mark.unit
def test_needs_migration_true_when_skeleton_or_version_absent():
    assert needs_migration({"functional_groups": {}}) is True  # missing fields/overrides/version
    assert needs_migration(
        {"fields": {}, "overrides": {}, "functional_groups": {}}
    ) is True  # missing version


@pytest.mark.unit
def test_needs_migration_false_for_fully_migrated_row():
    row = {"fields": {}, "overrides": {}, "functional_groups": {}, "version": 1}
    assert needs_migration(row) is False


_KEY_ATTRS = (schema.PARTITION_KEY_ATTR, schema.SORT_KEY_ATTR)


def _plan(row: dict):
    return plan_row_migration(
        row,
        row.get(schema.PARTITION_KEY_ATTR, "h-dcn"),
        key_attrs=_KEY_ATTRS,
        version_attr=schema.VERSION_ATTR,
        version_value="2026-10-26T00:00:00+00:00",
    )


@pytest.mark.unit
def test_plan_converts_groups_and_backfills_version_and_preserves_other_attrs():
    row = {
        schema.PARTITION_KEY_ATTR: "h-dcn",
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "fields": {"notes": {"key": "notes", "type": "string"}},
        "overrides": {"personal.gender": {"type": "enum"}},
        "functional_groups": [{"key": "personal", "order": 1}],
        "slug": "hdcn-application-form",  # an unrelated attribute must ride through verbatim
    }
    plan = _plan(row)
    assert plan.changed is True
    assert plan.before_group_shape == "list"
    assert plan.after_group_count == 1
    assert plan.version_backfilled is True
    # groups converted to MAP:
    assert plan.new_attributes["functional_groups"] == {
        "personal": {"key": "personal", "order": 1}
    }
    # version backfilled; unrelated attribute preserved; key excluded from the body.
    assert plan.new_attributes[schema.VERSION_ATTR] == "2026-10-26T00:00:00+00:00"
    assert plan.new_attributes["slug"] == "hdcn-application-form"
    assert plan.new_attributes["fields"] == {"notes": {"key": "notes", "type": "string"}}
    assert schema.PARTITION_KEY_ATTR not in plan.new_attributes


@pytest.mark.unit
def test_plan_backfills_absent_skeleton_parent_maps():
    row = {
        schema.PARTITION_KEY_ATTR: "fresh",
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "functional_groups": [{"key": "personal", "order": 1}],
        # fields / overrides / version all absent
    }
    plan = _plan(row)
    assert plan.changed is True
    assert plan.skeleton_backfilled is True
    assert plan.new_attributes["fields"] == {}
    assert plan.new_attributes["overrides"] == {}


@pytest.mark.unit
def test_plan_is_noop_for_already_migrated_row():
    row = {
        schema.PARTITION_KEY_ATTR: "h-dcn",
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "fields": {},
        "overrides": {},
        "functional_groups": {"personal": {"key": "personal", "order": 1}},
        "version": 7,
    }
    plan = _plan(row)
    assert plan.changed is False
    assert plan.new_attributes == {}


# ── 2. the migration INVARIANT against the REAL h-dcn row (both shapes) ─────────────────


def _resolved_via_reader(overlay: dict) -> dict:
    """Seed a reader with `overlay`'s stored slices and return the resolved field config as a
    stable keyed dict (fields keyed by field key, groups keyed by group key)."""
    table = FakeTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: overlay["tenant_id"],
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "fields": overlay["fields"],
            "overrides": overlay["overrides"],
            "functional_groups": overlay["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )
    config = FieldResolver(MembersProjectionReader(table=table)).resolve(overlay["tenant_id"])
    fields = {
        f.key: (f.functional_group, f.group, getattr(f.type, "value", f.type), f.order)
        for f in config.fields
    }
    groups = {g.key: (dict(g.label), g.order) for g in config.functional_groups}
    return {"fields": fields, "groups": groups}


@pytest.mark.unit
def test_migrated_list_row_resolves_identically_to_the_map_fixture():
    """MIGRATION INVARIANT (design C5 / R9, review harness-gap LIST→MAP): the LEGACY LIST real row,
    once its groups are converted by the migration transform, resolves byte-identically to the
    already-MAP real fixture — the migration changes STORAGE shape, never the RESOLVED view."""
    legacy = _load(_LIST_FIXTURE)
    legacy.pop("_comment", None)

    # Resolve the legacy row AS-IS (dual-read already handles the LIST) ...
    before = _resolved_via_reader(legacy)

    # ... then migrate its groups to MAP and resolve again — the resolved view must be identical.
    migrated = dict(legacy)
    migrated["functional_groups"] = convert_functional_groups(legacy["functional_groups"])
    after = _resolved_via_reader(migrated)

    assert before == after, (
        "the LIST→MAP migration must not change the resolved field config — storage shape only"
    )
    # And the full 6-group catalog survives the conversion (no truncation).
    assert set(after["groups"]) == {
        "personal",
        "address",
        "membership",
        "motor",
        "financial",
        "administrative",
    }


@pytest.mark.unit
def test_committed_map_fixture_and_legacy_list_fixture_carry_the_same_catalog():
    """Belt-and-suspenders: the migrated committed fixture (MAP) and the legacy fixture (LIST) name
    the SAME functional-group catalog, so the two committed real-data fixtures cannot drift."""
    map_groups = set(convert_functional_groups(_load(_MAP_FIXTURE)["functional_groups"]))
    list_groups = set(
        convert_functional_groups(_load(_LIST_FIXTURE)["functional_groups"])
    )
    assert list_groups == map_groups == {
        "personal",
        "address",
        "membership",
        "motor",
        "financial",
        "administrative",
    }
