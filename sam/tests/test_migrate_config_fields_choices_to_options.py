"""
03a C7 — unit tests for the ``choices`` -> ``options`` backfill migration
(``scripts/migrate_config_fields_choices_to_options.py``).

Two layers, both without AWS / boto3 (steering 34/39):

1. **Pure planner** (:func:`options_from_choices`, :func:`plan_choices_to_options`) — tested
   against the COMMITTED REAL fixtures that mirror the live h-dcn ``config#fields`` row
   (``hdcn_config_fields_overlay.json`` — ``personal.gender`` under rich-dict ``choices`` — and
   ``..._legacy_groups_list.json``), never a hand-built shape (steering 39: *trust runs, not
   inference*). Covers the two legacy value shapes (bare string + rich dict), malformed-drop, and
   the IDEMPOTENCE pivot (an ``options``-only entry plans nothing).

2. **Live driver** (:func:`migrate_tenant`) — driven over an in-memory ``FakeTable`` wired to the
   REAL reader + REAL Change-Op write repository + REAL ``ConfigFieldsCrudService`` (no mocking of
   the write mechanics). Proves the rewrite goes through the Change-Op ``update_item`` path as TWO
   scoped ops (03a C2↔C7 coupling): a ``SET <map>.<key>.options`` via ``set_field`` then a
   ``REMOVE <map>.<key>.choices`` via the dedicated ``remove_legacy_choices`` op — NOT a whole-row
   ``put_item`` replace (R3.3 / steering 39). (C2 retired ``choices`` from the write surface, so a
   single ``{"options":..., "choices": None}`` call is no longer possible — it would be rejected by
   ``set_field``'s attr-surface guard; the migration uses the legacy-removal op instead.) It also
   proves the real h-dcn ``referral_source``-shaped vocabulary survives as value-only ``options``,
   and that a re-run is a no-op (idempotence).

3. **Kind-aware DROP-not-convert** (section 4) — a SCOPE-BACKED field (stored spec carries an
   enabled ``scope``) carrying legacy ``choices`` + a stale inline ``options`` is DRIVEN over the
   SAME real service + real writer, proving the W2 write-edge guard is actually exercised: the
   migration must NOT convert (``set_field`` with inline options would be rejected by W2) but DROP
   both the legacy ``choices`` and the stale inline ``options`` so the field sources purely from the
   ``config#scope`` dimension. This is the C7↔C2/W2 correction (real case: h-dcn field ``region``).

**Validates: Requirements 2.1** · **Components: C7**
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


# ── Load the migration module from scripts/ (not an importable package) ─────────────────────
def _load_migration_module():
    path = os.path.join(_REPO_ROOT, "scripts", "migrate_config_fields_choices_to_options.py")
    spec = importlib.util.spec_from_file_location("migrate_config_fields_choices_to_options", path)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so dataclass machinery can resolve cls.__module__
    # (a module-level @dataclass with a default_factory looks the module up in sys.modules).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mig = _load_migration_module()

from services import projection_schema as schema  # noqa: E402

from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService  # noqa: E402
from sam.members.domain.field_resolver import FieldResolver  # noqa: E402
from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    MembersConfigWriteRepository,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure planner — value-shape reduction
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_options_from_choices_bare_strings_become_value_only_options():
    assert mig.options_from_choices(["man", "vrouw", "other"]) == [
        {"value": "man"},
        {"value": "vrouw"},
        {"value": "other"},
    ]


@pytest.mark.unit
def test_options_from_choices_rich_dicts_reduce_to_value_only():
    # The REAL h-dcn personal.gender shape: rich dicts {value, label} -> value-only options.
    rich = [
        {"value": "man", "label": {"en": "Man", "nl": "Man"}},
        {"value": "vrouw", "label": {"en": "Female", "nl": "Vrouw"}},
    ]
    assert mig.options_from_choices(rich) == [{"value": "man"}, {"value": "vrouw"}]


@pytest.mark.unit
def test_options_from_choices_drops_malformed_never_fabricates():
    # A dict with no value, an empty/blank string, and a non-str/non-dict entry are all dropped.
    mixed = ["keep", "  ", {"label": {"en": "no value"}}, {"value": "also_keep"}, 42, {"value": ""}]
    assert mig.options_from_choices(mixed) == [{"value": "keep"}, {"value": "also_keep"}]


@pytest.mark.unit
def test_options_from_choices_preserves_order():
    assert mig.options_from_choices(["c", "a", "b"]) == [
        {"value": "c"},
        {"value": "a"},
        {"value": "b"},
    ]


@pytest.mark.unit
def test_options_from_choices_non_list_is_empty():
    assert mig.options_from_choices(None) == []
    assert mig.options_from_choices("man") == []  # a bare string is NOT a choices list
    assert mig.options_from_choices({}) == []


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2. Pure planner — enumeration over the REAL committed fixtures
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_plan_selects_the_real_hdcn_gender_override_carrying_choices():
    overlay = _load_fixture("hdcn_config_fields_overlay.json")
    # The fixture stores overrides under "overrides" at rest (the storage key).
    plans = mig.plan_choices_to_options(overlay)

    keys = {(p.map_name, p.entry_key) for p in plans}
    assert ("overrides", "personal.gender") in keys, (
        "the real h-dcn personal.gender override carries bare `choices` and must be planned"
    )
    gender = next(p for p in plans if p.entry_key == "personal.gender")
    # The real gender choices are the two rich dicts {man, vrouw}; reduce to value-only options.
    assert gender.options == [{"value": "man"}, {"value": "vrouw"}]
    assert gender.field_key == "personal.gender"  # dotted identity accepted by the service
    assert gender.dropped == 0


@pytest.mark.unit
def test_plan_selects_the_legacy_groups_list_fixture_gender_override():
    overlay = _load_fixture("hdcn_config_fields_overlay_legacy_groups_list.json")
    plans = mig.plan_choices_to_options(overlay)
    assert [(p.map_name, p.entry_key) for p in plans] == [("overrides", "personal.gender")]
    assert plans[0].options == [{"value": "man"}]


@pytest.mark.unit
def test_plan_is_empty_when_no_entry_carries_choices_idempotence_pivot():
    # Simulate the POST-migration shape: options present, choices absent -> nothing to plan.
    overlay = {
        "fields": {},
        "overrides": {
            "personal.gender": {
                "type": "enum",
                "options": [{"value": "man"}, {"value": "vrouw"}],
                "order": 60,
            }
        },
    }
    assert mig.plan_choices_to_options(overlay) == []


@pytest.mark.unit
def test_plan_still_migrates_an_entry_that_has_both_choices_and_options():
    # A half-migrated entry still carrying stale `choices` MUST be planned so choices is dropped;
    # options is rebuilt deterministically from the choices values.
    overlay = {
        "fields": {},
        "overrides": {
            "personal.gender": {
                "type": "enum",
                "choices": ["man", "vrouw"],
                "options": [{"value": "STALE"}],
            }
        },
    }
    plans = mig.plan_choices_to_options(overlay)
    assert len(plans) == 1
    assert plans[0].options == [{"value": "man"}, {"value": "vrouw"}]


@pytest.mark.unit
def test_plan_enumerates_variable_fields_under_fields_map():
    overlay = {
        "fields": {"referral_source": {"type": "enum", "choices": ["internet", "facebook"]}},
        "overrides": {},
    }
    plans = mig.plan_choices_to_options(overlay)
    assert [(p.map_name, p.entry_key, p.field_key) for p in plans] == [
        ("fields", "referral_source", "referral_source")
    ]
    assert plans[0].options == [{"value": "internet"}, {"value": "facebook"}]


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3. Live driver over the REAL reader + Change-Op write repository (no mocked write)
# ═══════════════════════════════════════════════════════════════════════════════════════════

_TENANT = "c7-tenant"
_vc = 0


def _version():
    global _vc
    _vc += 1
    return f"v-c7-{_vc:06d}"


class FakeTable:
    """In-memory DynamoDB Table stand-in supporting the ops the Change-Op path uses.

    Implements query (reader), get_item / put_item / update_item / delete_item (writer +
    skeleton), with a minimal SET/REMOVE UpdateExpression evaluator over ExpressionAttributeNames /
    Values. This exercises the REAL ``apply_ops`` named-path ``update_item`` — so the test proves
    the migration never issues a whole-row ``put_item`` replace on the Change-Op path.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.put_item_calls = 0
        self.update_item_calls = 0

    # -- reader side -- (accept + ignore ConsistentRead and other query kwargs)
    def query(self, KeyConditionExpression=None, **_kwargs):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}

    # -- writer side --
    def _key_tuple(self, Key):
        return (Key[schema.PARTITION_KEY_ATTR], Key[schema.SORT_KEY_ATTR])

    def get_item(self, Key=None, **_kwargs):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(self, Item=None, ConditionExpression=None, ExpressionAttributeNames=None):
        self.put_item_calls += 1
        key = (Item[schema.PARTITION_KEY_ATTR], Item[schema.SORT_KEY_ATTR])
        if ConditionExpression and "attribute_not_exists" in str(ConditionExpression):
            if key in self.store:
                from botocore.exceptions import ClientError

                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
                )
        self.store[key] = dict(Item)

    def update_item(
        self,
        Key=None,
        UpdateExpression=None,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        self.update_item_calls += 1
        key = self._key_tuple(Key)
        item = self.store.get(key)
        if item is None:
            # The migration only ever updates an existing (seeded) row.
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
            )
        item = dict(item)
        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}
        self._apply_update_expression(item, UpdateExpression, names, values)
        self.store[key] = item

    @staticmethod
    def _resolve_path(item, segments, names):
        resolved = [names.get(s, s) for s in segments]
        return resolved

    def _apply_update_expression(self, item, expr, names, values):
        # Split into SET ... and REMOVE ... clauses (the two verbs apply_ops emits).
        set_part = ""
        remove_part = ""
        if "REMOVE " in expr:
            head, remove_part = expr.split("REMOVE ", 1)
            set_part = head.replace("SET ", "", 1).strip() if "SET " in head else ""
        elif expr.startswith("SET "):
            set_part = expr[len("SET "):].strip()
        for clause in [c for c in set_part.split(",") if c.strip()]:
            path_expr, val_ph = clause.split("=", 1)
            segs = self._resolve_path(item, path_expr.strip().split("."), names)
            self._set_at(item, segs, values[val_ph.strip()])
        for clause in [c for c in remove_part.split(",") if c.strip()]:
            segs = self._resolve_path(item, clause.strip().split("."), names)
            self._remove_at(item, segs)

    @staticmethod
    def _set_at(item, segs, value):
        node = item
        for s in segs[:-1]:
            node = node.setdefault(s, {})
        node[segs[-1]] = value

    @staticmethod
    def _remove_at(item, segs):
        node = item
        for s in segs[:-1]:
            if not isinstance(node.get(s), dict):
                return
            node = node[s]
        node.pop(segs[-1], None)


def _seed_real_row(table, *, overrides):
    table.put_item(
        Item={
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "fields": {},
            "overrides": overrides,
            "functional_groups": {},
            schema.VERSION_ATTR: "v-seed",
        }
    )


def _seed_variable_field_row(table, *, fields):
    table.put_item(
        Item={
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            "fields": fields,
            "overrides": {},
            "functional_groups": {},
            schema.VERSION_ATTR: "v-seed",
        }
    )


def _service_and_reader(table):
    reader = MembersProjectionReader(table=table)
    writer = MembersConfigWriteRepository(table=table, version_fn=_version)
    service = ConfigFieldsCrudService(writer, reader=reader)
    return service, reader


@pytest.mark.unit
def test_migrate_tenant_rewrites_real_gender_choices_to_value_only_options():
    # Seed the REAL h-dcn personal.gender shape (rich-dict choices, options absent).
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_real_row(table, overrides={"personal.gender": dict(real_gender)})
    service, reader = _service_and_reader(table)

    plans = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert [p.entry_key for p in plans] == ["personal.gender"]

    # Read the row back: choices is GONE, options carries the value-only vocabulary.
    stored = table.get_item(
        Key=schema.build_key(
            _TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields")
        )
    )["Item"]
    entry = stored["overrides"]["personal.gender"]
    assert "choices" not in entry, "legacy `choices` must be dropped"
    assert entry["options"] == [{"value": "man"}, {"value": "vrouw"}]
    # Sibling attrs on the SAME entry survived (no whole-row / whole-entry replace).
    assert entry["type"] == "enum"
    assert entry["order"] == 60


@pytest.mark.unit
def test_migrate_tenant_uses_change_op_update_item_never_whole_row_put():
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_real_row(table, overrides={"personal.gender": dict(real_gender)})
    puts_before = table.put_item_calls
    service, reader = _service_and_reader(table)

    mig.migrate_tenant(_TENANT, service=service, reader=reader)

    # Two scoped Change-Ops per entry: a SET options (set_field) + a REMOVE choices
    # (remove_legacy_choices) — each its own version-conditional update_item.
    assert table.update_item_calls >= 2, (
        "the rewrite must go through update_item as TWO scoped ops (SET options + REMOVE choices)"
    )
    assert table.put_item_calls == puts_before, (
        "the migration must NOT issue a whole-row put_item replace (R3.3 / steering 39)"
    )


@pytest.mark.unit
def test_migrate_tenant_is_idempotent_rerun_is_a_noop():
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_real_row(table, overrides={"personal.gender": dict(real_gender)})
    service, reader = _service_and_reader(table)

    first = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert len(first) == 1
    updates_after_first = table.update_item_calls

    # Re-run: the row now has options and no choices -> nothing to plan, nothing to write.
    second = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert second == [], "a re-run must plan nothing (idempotent)"
    assert table.update_item_calls == updates_after_first, "a re-run must not write"


@pytest.mark.unit
def test_migrated_row_resolves_six_values_as_options_through_resolver():
    # The EXPECTED OUTCOME framing from the task: a referral_source-shaped 6-value vocabulary
    # survives as value-only options after migration, read through the resolver.
    six = ["internet", "facebook", "bigtwin", "family", "other", "young-ones"]
    table = FakeTable()
    # referral_source is a tenant VARIABLE field (not a registry/base field), so it lives under
    # the `fields` map keyed by its bare key — the real h-dcn shape for an added selectable field.
    _seed_variable_field_row(
        table,
        fields={"referral_source": {"type": "enum", "choices": list(six)}},
    )
    service, reader = _service_and_reader(table)

    mig.migrate_tenant(_TENANT, service=service, reader=reader)

    cfg = FieldResolver(MembersProjectionReader(table=table)).resolve(_TENANT)
    field = next((f for f in cfg.fields if f.key == "referral_source"), None)
    assert field is not None
    assert [o.value for o in (field.options or [])] == six, (
        "all 6 referral_source values must survive as value-only options after migration"
    )


@pytest.mark.unit
def test_migrate_tenant_no_choices_row_is_a_noop():
    table = FakeTable()
    _seed_real_row(
        table,
        overrides={"personal.gender": {"type": "enum", "options": [{"value": "man"}]}},
    )
    service, reader = _service_and_reader(table)
    plans = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert plans == []
    assert table.update_item_calls == 0


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 4. SCOPE-BACKED (W2) legacy-`choices` entry — DROP-not-convert (the C7↔C2/W2 correction)
# ═══════════════════════════════════════════════════════════════════════════════════════════
#
# The bug this guards: a scope-backed field (stored spec carries an enabled `scope`) that still
# holds legacy `choices` (and a stale inline `options`) must NOT be converted to inline `options`
# — the W2 write-edge guard REJECTS inline options on a scope-backed field, so a convert CRASHES.
# The migration must DROP both the legacy `choices` and the stale inline `options` so the field
# sources purely from the config#scope dimension. Driven over the REAL ConfigFieldsCrudService +
# REAL writer over the FakeTable, so W2 is actually exercised (the test that would have caught the
# bug). The real h-dcn case was tenant h-dcn field `region`.


class _SetFieldSpy:
    """Wraps the real service, recording every ``set_field`` call so a test can PROVE the migration
    never hands a scope-backed/reference field an inline `options` payload (which W2/W1 would
    reject). Every other method delegates to the real service unchanged — so W1/W2, the Change-Op
    writer, and apply_ops are all the REAL implementations (no mocked write mechanics)."""

    def __init__(self, service):
        self._service = service
        self.set_field_calls: list[dict] = []

    def set_field(self, tenant_id, field_key, def_attrs, **kwargs):
        self.set_field_calls.append({"field_key": field_key, "def_attrs": dict(def_attrs)})
        return self._service.set_field(tenant_id, field_key, def_attrs, **kwargs)

    def __getattr__(self, name):
        return getattr(self._service, name)


@pytest.mark.unit
def test_migrate_tenant_scope_backed_field_drops_choices_and_stale_options_no_convert():
    # A scope-backed field (enabled `scope`) carrying BOTH legacy `choices` and a stale inline
    # `options` — the exact shape that CRASHED the naive convert on the W2 guard (h-dcn `region`).
    table = FakeTable()
    _seed_variable_field_row(
        table,
        fields={
            "region": {
                "type": "enum",
                "scope": {"enabled": True},
                "choices": ["noord", "zuid"],
                "options": [{"value": "STALE"}],
                "functional_group": "membership",
            }
        },
    )
    real_service, reader = _service_and_reader(table)
    service = _SetFieldSpy(real_service)

    plans = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert [p.entry_key for p in plans] == ["region"]

    # W2 is exercised by the REAL service: the migration must NEVER hand `region` an inline
    # `options` payload (that is exactly what set_field's W2 guard rejects) — so set_field is not
    # called for it at all (drop-not-convert uses the dedicated removal ops only).
    region_set_field_calls = [
        c for c in service.set_field_calls if c["field_key"] == "region"
    ]
    assert region_set_field_calls == [], (
        "a scope-backed field must NOT be converted via set_field({'options': ...}) — W2 rejects "
        "inline options; the migration must DROP the legacy vocabulary instead"
    )

    # The stored row: BOTH the legacy `choices` and the stale inline `options` are gone, so the
    # field sources purely from the config#scope dimension. The scope sub-object survives.
    stored = table.get_item(
        Key=schema.build_key(
            _TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields")
        )
    )["Item"]
    entry = stored["fields"]["region"]
    assert "choices" not in entry, "legacy `choices` must be dropped on a scope-backed field"
    assert "options" not in entry, "stale inline `options` must be dropped on a scope-backed field"
    assert entry["scope"] == {"enabled": True}, "the scope sub-object (the real source) survives"
    assert entry["functional_group"] == "membership", "sibling attrs survive (no whole-row replace)"


@pytest.mark.unit
def test_migrate_tenant_scope_backed_uses_update_item_never_whole_row_put():
    table = FakeTable()
    _seed_variable_field_row(
        table,
        fields={
            "region": {
                "type": "enum",
                "scope": {"enabled": True},
                "choices": ["noord", "zuid"],
                "options": [{"value": "STALE"}],
            }
        },
    )
    puts_before = table.put_item_calls
    service, reader = _service_and_reader(table)

    mig.migrate_tenant(_TENANT, service=service, reader=reader)

    # Two scoped Change-Ops for the drop: REMOVE choices + REMOVE options — each its own
    # version-conditional update_item; never a whole-row put_item replace.
    assert table.update_item_calls >= 2, (
        "the drop must go through update_item as scoped REMOVE ops (choices + stale options)"
    )
    assert table.put_item_calls == puts_before, (
        "the migration must NOT issue a whole-row put_item replace (R3.3 / steering 39)"
    )


@pytest.mark.unit
def test_migrate_tenant_scope_backed_rerun_is_a_noop():
    table = FakeTable()
    _seed_variable_field_row(
        table,
        fields={
            "region": {
                "type": "enum",
                "scope": {"enabled": True},
                "choices": ["noord", "zuid"],
                "options": [{"value": "STALE"}],
            }
        },
    )
    service, reader = _service_and_reader(table)

    first = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert [p.entry_key for p in first] == ["region"]
    updates_after_first = table.update_item_calls

    # Re-run: `choices` is gone so nothing is planned, and nothing is written (idempotent).
    second = mig.migrate_tenant(_TENANT, service=service, reader=reader)
    assert second == [], "a re-run must plan nothing (idempotent) once choices is dropped"
    assert table.update_item_calls == updates_after_first, "a re-run must not write"


@pytest.mark.unit
def test_migrate_tenant_scope_backed_only_choices_no_stale_options_drops_choices():
    # Scope-backed with ONLY legacy choices (no stale inline options): still drop-not-convert,
    # and remove_inline_options is a safe no-op (nothing to drop there).
    table = FakeTable()
    _seed_variable_field_row(
        table,
        fields={"region": {"type": "enum", "scope": {"enabled": True}, "choices": ["noord"]}},
    )
    service, reader = _service_and_reader(table)

    mig.migrate_tenant(_TENANT, service=service, reader=reader)

    entry = table.get_item(
        Key=schema.build_key(
            _TENANT, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields")
        )
    )["Item"]["fields"]["region"]
    assert "choices" not in entry
    assert "options" not in entry, "no inline options is created for a scope-backed field"


@pytest.mark.unit
def test_classify_entry_kind_matches_write_edge_guards():
    # The migration's CONVERT-vs-DROP classifier reuses the service's W1/W2 predicates, so it can
    # never disagree with what set_field would actually reject.
    assert mig.classify_entry_kind("region", {"type": "enum", "scope": {"enabled": True}}) == (
        "scope-backed"
    )
    assert mig.classify_entry_kind("some_ref", {"type": "reference"}) == "reference"
    assert mig.classify_entry_kind("gender", {"type": "enum"}) == "inline-enum"
    # An explicitly-disabled scope is NOT scope-backed (matches _is_scope_backed_field).
    assert mig.classify_entry_kind("x", {"type": "enum", "scope": {"enabled": False}}) == (
        "inline-enum"
    )
