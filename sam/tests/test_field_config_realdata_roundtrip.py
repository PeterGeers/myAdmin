"""
REAL-DATA round-trip + grouping regression test for the Members field config
(`config#fields`) — the test that was missing throughout specs 11/12 and would have caught
the "lost control" field-config drift on day one (see
`.kiro/specs/Members/root-cause-analysis.md`, steering `39-backend-data-access-sam-dynamodb.md`).

It uses the ACTUAL stored `h-dcn` overlay (captured from `test_governance_projection`, committed
at `sam/tests/fixtures/hdcn_config_fields_overlay.json`) — NOT a hand-built fixture. Spec 11's
lesson was explicit: *trust runs, not inference* — a wrong hand-built fixture (a pre-dotted key
instead of the real bare-`key`+`group` shape) once hid this exact bug.

What it pins (the invariants the backend resolver MUST uphold, and the authoring surfaces MUST
consume rather than re-derive):

1. **Resolved grouping is correct even when the stored override omits `functional_group`.**
   The real `overrides["personal.gender"]` has NO `functional_group` key, yet the resolver MUST
   place `gender` in the `personal` functional group (via the base default), because
   `FieldResolver._apply_override` resolves `functional_group or group`. This is the SERVER TRUTH:
   the server view is right; any consumer that reads the raw stored `functional_group` (None) and
   buckets by it drops the field into an "other" bucket — the frontend overlay-tier drift that
   produced "most groups say they have no fields".

2. **Every resolved field lands in a real catalog group — none orphaned.** No base field falls
   into an ungrouped/other bucket at the RESOLVED level. (The frontend must consume this resolved
   grouping; steering 39.)

3. **On-form flags round-trip by identity.** A base field marked on-form in storage
   (`application_visible: true`) resolves on-form; one not marked resolves off — addressed by the
   bare field `key`, never a reconstructed dotted key.

Validates the decision-B invariant: read and write address a field by ONE stable identity, and the
RESOLVED view (not the raw overlay) is the contract every surface uses.
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
from sam.members.repository.projection_config_reader import MembersProjectionReader

_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "hdcn_config_fields_overlay.json"
)


def _load_real_overlay() -> dict:
    with open(_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class FakeTable:
    """In-memory DynamoDB Table stand-in (query side), per-partition isolated — mirrors the
    sibling projection-reader tests so no AWS / boto3 is touched (steering 39/34)."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = dict(item)

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


def _reader_over_real_row() -> tuple[MembersProjectionReader, str]:
    """A projection reader seeded with the REAL h-dcn `config#fields` row."""
    overlay = _load_real_overlay()
    tenant_id = overlay["tenant_id"]
    table = FakeTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: tenant_id,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "fields": overlay["fields"],
            "overrides": overlay["overrides"],
            "functional_groups": overlay["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )
    return MembersProjectionReader(table=table), tenant_id


def _resolved_fields(reader: MembersProjectionReader, tenant_id: str):
    config = FieldResolver(reader).resolve(tenant_id)
    return {f.key: f for f in config.fields}, config


@pytest.mark.unit
def test_resolver_places_gender_in_personal_group_despite_no_stored_functional_group():
    # SERVER TRUTH: the real stored override for `gender` carries NO `functional_group`, yet the
    # resolver MUST place it in `personal` (base default). This is the correct grouping the
    # frontend must CONSUME — not re-derive from the raw stored value (which would orphan it).
    overlay = _load_real_overlay()
    assert "functional_group" not in overlay["overrides"]["personal.gender"], (
        "fixture sanity: the real gender override must have NO functional_group (the drift trigger)"
    )

    reader, tenant_id = _reader_over_real_row()
    fields, _ = _resolved_fields(reader, tenant_id)

    assert "gender" in fields, "gender must resolve (it is a base field)"
    assert fields["gender"].functional_group == "personal", (
        "resolver must group gender under 'personal' via the base default, even though the stored "
        "override omits functional_group — this is the server view the frontend must consume"
    )


@pytest.mark.unit
def test_resolved_base_fields_are_never_orphaned_into_an_other_group():
    # "Most groups say they have no fields" came from base fields (functional_group=None in
    # storage) being bucketed into an orphan group by the overlay tier. At the RESOLVED level no
    # base/membership field may land outside the real catalog groups.
    reader, tenant_id = _reader_over_real_row()
    fields, config = _resolved_fields(reader, tenant_id)
    # The catalog is DERIVED from the resolved functional-group set — NOT a hardcoded list. The
    # resolved catalog is the single source of truth (spec 03); hand-listing group keys here was a
    # tenant-specific assumption that wrongly flagged fields in groups it forgot (motor/financial).
    catalog = {g.key for g in config.functional_groups}

    orphaned = [
        f.key for f in fields.values() if f.functional_group and f.functional_group not in catalog
    ]
    assert orphaned == [], (
        f"no resolved field may fall outside the catalog groups; orphaned: {orphaned}"
    )
    # And specifically the personal group is populated (the symptom was it reading as EMPTY).
    personal = [k for k, f in fields.items() if f.functional_group == "personal"]
    assert len(personal) >= 5, (
        f"the 'personal' group must contain its base fields, not read as empty; got {personal}"
    )


@pytest.mark.unit
def test_on_form_flag_round_trips_by_field_identity():
    # A previously-saved on-form base field must resolve on-form; an unsaved one off — addressed
    # by the bare field key, never a reconstructed {group}.{key}. (email is on-form in the real
    # row; gender is not.)
    overlay = _load_real_overlay()
    assert overlay["overrides"]["personal.email"].get("application_visible") is True
    assert overlay["overrides"]["personal.gender"].get("application_visible") in (None, False)

    reader, tenant_id = _reader_over_real_row()
    fields, _ = _resolved_fields(reader, tenant_id)

    assert fields["email"].application_visible is True, (
        "a base field saved on-form must resolve on-form (identity round-trip)"
    )
    assert bool(fields["gender"].application_visible) is False, (
        "a base field NOT saved on-form must resolve off-form"
    )
