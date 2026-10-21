"""
S5b Task 8.1 — unit tests for the Members module projection config reader.

Covers :class:`sam.members.repository.projection_config_reader.MembersProjectionReader`
— the read-only seam that feeds the S5 domain from the governance projection (design C4):

- ``config#scope``  → :class:`ScopeConfig` round-trip (incl. multiple dimensions);
- a missing ``config#scope`` → tenant-wide empty ``ScopeConfig`` (R1.6);
- ``config#fields`` → :class:`TenantOverlay` (incl. ``FieldType`` conversion + overrides
  carrying only the aspects present) (R1.5);
- a missing ``config#fields`` → empty ``TenantOverlay`` (R1.7);
- ``scopegrant#<email>#<dimension>`` → ``{dimension: values}`` filtered to the caller's
  email, with ``["*"]`` all-access preserved and a missing grant absent from the map (R2.3);
- one ``Query`` per partition (per-invocation cache) + tenant isolation (only the queried
  partition answers, R7.4).

DynamoDB is faked with an in-memory ``FakeTable`` (mirrors
``sam/tests/test_projection_governance_reader.py``): its
``query(KeyConditionExpression=...)`` returns ONLY the seeded items whose partition key
matches the boto3 ``Key(...).eq(...)`` condition, so cross-tenant items are never returned.
No live AWS, no MySQL.
"""

import os
import sys

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_projection_governance_reader.py — the projection schema is the single source of truth
# for the key shape, shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.field_resolver import TenantOverlay
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.repository.projection_config_reader import MembersProjectionReader

# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (read side)
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only).

    Stores items keyed by (tenant_id, sk). ``query(KeyConditionExpression=...)`` extracts the
    requested tenant from the boto3 ``Key(...).eq(...)`` condition and returns ONLY that
    partition's items (cross-tenant items are never returned). Counts queries per tenant so
    tests can assert the reader's per-invocation cache reads each partition at most once.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.query_counts: dict[str, int] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = _tenant_from_condition(KeyConditionExpression)
        self.query_counts[tenant_id] = self.query_counts.get(tenant_id, 0) + 1
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _tenant_from_condition(condition):
    """Extract the partition-key value from a boto3 ``Key(...).eq(...)`` condition."""
    expr = condition.get_expression()
    return expr["values"][1]


# ---------------------------------------------------------------------------
# Seed helpers (use the canonical schema builders so keys match production)
# ---------------------------------------------------------------------------


def _config_scope_item(tenant_id, dimensions, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
        "dimensions": dimensions,
        schema.VERSION_ATTR: version,
    }


def _config_fields_item(tenant_id, fields, overrides, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, "fields"
        ),
        "fields": fields,
        "overrides": overrides,
        schema.VERSION_ATTR: version,
    }


def _scopegrant_item(tenant_id, email, dimension, values, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_SCOPEGRANT, email, dimension
        ),
        "dimension": dimension,
        "values": values,
        schema.VERSION_ATTR: version,
    }


def _region_dimension_dict(**overrides):
    base = {
        "key": "region",
        "field": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "required_for": ["Members_CRUD"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# get_scope_config — config#scope → ScopeConfig round-trip
# ---------------------------------------------------------------------------


class TestGetScopeConfig:
    def test_get_scope_config_single_dimension_round_trips_to_scope_config(self):
        table = FakeTable()
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("h-dcn")

        assert isinstance(config, ScopeConfig)
        assert config.tenant_id == "h-dcn"
        assert len(config.dimensions) == 1
        dim = config.dimensions[0]
        assert dim.key == "region"
        assert dim.label == {"nl": "Regio", "en": "Region"}
        assert dim.enabled is True
        assert dim.field == "region"
        assert tuple(dim.values) == ("Noord", "Zuid", "Oost", "West")
        assert tuple(dim.required_for) == ("Members_CRUD",)

    def test_get_scope_config_multiple_dimensions_round_trips_all(self):
        table = FakeTable()
        season = {
            "key": "season",
            "field": "season",
            "label": {"en": "Season"},
            "enabled": True,
            "values": ["2023", "2024"],
            "required_for": [],
        }
        table.put(_config_scope_item("multi", [_region_dimension_dict(), season]))

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("multi")

        assert [d.key for d in config.dimensions] == ["region", "season"]
        season_dim = config.dimension("season")
        assert season_dim is not None
        assert season_dim.field == "season"
        assert tuple(season_dim.values) == ("2023", "2024")

    def test_get_scope_config_missing_row_collapses_to_tenant_wide_empty(self):
        table = FakeTable()  # nothing seeded for this tenant
        reader = MembersProjectionReader(table=table)

        config = reader.get_scope_config("unconfigured")

        assert isinstance(config, ScopeConfig)
        assert config.tenant_id == "unconfigured"
        assert config.dimensions == ()
        assert config.is_tenant_wide() is True

    def test_get_scope_config_disabled_dimension_preserved_as_data(self):
        table = FakeTable()
        table.put(
            _config_scope_item(
                "h-dcn", [_region_dimension_dict(enabled=False, values=[])]
            )
        )

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("h-dcn")

        # A disabled dimension is preserved (a no-op) — the tenant collapses to tenant-wide.
        assert len(config.dimensions) == 1
        assert config.dimensions[0].enabled is False
        assert config.is_tenant_wide() is True


# ---------------------------------------------------------------------------
# get_overlay — config#fields → TenantOverlay
# ---------------------------------------------------------------------------


class TestGetOverlay:
    def test_get_overlay_builds_variable_fields_with_field_type_conversion(self):
        table = FakeTable()
        fields = {
            "motor_type": {
                "key": "motor_type",
                "type": "enum",
                "required": True,
                "label": {"nl": "Motor", "en": "Motorcycle"},
                "choices": ["Sport", "Touring"],
                "visible": True,
                "order": 5,
            },
            "note": {
                "key": "note",
                "type": "string",
                "required": False,
                "label": {},
                "choices": None,
                "visible": True,
                "order": 6,
            },
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert isinstance(overlay, TenantOverlay)
        motor = overlay.fields["motor_type"]
        assert motor.type is FieldType.ENUM  # string "enum" -> FieldType.ENUM
        assert motor.required is True
        assert motor.label == {"nl": "Motor", "en": "Motorcycle"}
        assert tuple(motor.choices) == ("Sport", "Touring")
        assert motor.order == 5
        # choices=None stays None (not an empty tuple).
        assert overlay.fields["note"].choices is None
        assert overlay.fields["note"].type is FieldType.STRING

    def test_get_overlay_unknown_field_type_defaults_to_string(self):
        table = FakeTable()
        fields = {
            "weird": {"key": "weird", "type": "not-a-real-type"},
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert overlay.fields["weird"].type is FieldType.STRING

    def test_get_overlay_override_carries_only_present_aspects(self):
        table = FakeTable()
        overrides = {
            # Only 'label' + 'order' present — 'visible'/'required' must stay None.
            "personal.first_name": {"label": {"nl": "Volledige naam"}, "order": 1},
            # Only 'visible' present.
            "personal.street": {"visible": False},
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        name_ov = overlay.overrides["personal.first_name"]
        assert name_ov.label == {"nl": "Volledige naam"}
        assert name_ov.order == 1
        assert name_ov.visible is None  # absent -> leave base as-is
        assert name_ov.required is None

        addr_ov = overlay.overrides["personal.street"]
        assert addr_ov.visible is False
        assert addr_ov.label is None
        assert addr_ov.required is None
        assert addr_ov.order is None
        assert addr_ov.functional_group is None  # absent -> leave base as-is

    def test_get_overlay_override_carries_functional_group(self):
        """A projected fixed-field override's functional_group reaches the overlay (R4.9).

        The authored ``members.field_overlay.fixed_overrides[dotted].functional_group`` is
        projected onto ``config#fields.overrides[dotted].functional_group`` and must be
        reconstructed onto ``FixedFieldOverride.functional_group`` so ``FieldResolver`` can
        reassign the field's display group.
        """
        table = FakeTable()
        overrides = {
            "personal.street": {"functional_group": "address"},
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert overlay.overrides["personal.street"].functional_group == "address"

    def test_get_overlay_override_sources_enum_options_from_choices(self):
        """A fixed-enum override's values authored under ``choices`` reach ``options`` (regression).

        The authoring UI (field_overlay) and the legacy Flask builder write a fixed enum field's
        value list (e.g. ``membership.status``) under ``choices`` ([{value,label}]), not
        ``options``. The reader must source the override's ``options`` from ``choices`` when
        ``options`` is absent — else a tenant-authored value (here ``died``) is silently dropped and
        ``FieldResolver`` falls back to the fixed field's base choices (the config#fields enum-choices
        data-loss on read; findings.md).
        """
        table = FakeTable()
        overrides = {
            "membership.status": {
                "choices": [
                    {"value": "active", "label": {"nl": "Actief", "en": "Active"}},
                    {"value": "died", "label": {"nl": "Overleden", "en": "Died"}},
                ]
            }
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        opts = overlay.overrides["membership.status"].options
        assert opts is not None
        assert tuple(o.value for o in opts) == ("active", "died")

    def test_get_overlay_override_options_takes_precedence_over_choices(self):
        """When BOTH ``options`` and ``choices`` are present on an override, ``options`` wins."""
        table = FakeTable()
        overrides = {
            "membership.status": {
                "options": [{"value": "from_options"}],
                "choices": [{"value": "from_choices"}],
            }
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        opts = reader.get_overlay("h-dcn").overrides["membership.status"].options
        assert tuple(o.value for o in opts) == ("from_options",)

    def test_get_overlay_variable_field_carries_scope_attribute(self):
        """Phase 3 step 9 (R2.1): a projected field `scope` attribute → FieldScope (SAM read repr).

        The authoring/read re-presentation of scope-binding as a field attribute. The scope
        RESOLUTION still consumes config#scope / ScopeConfig unchanged (R2.3) — this carries
        the attribute verbatim onto the overlay field.
        """
        table = FakeTable()
        fields = {
            "region": {
                "key": "region",
                "type": "enum",
                "choices": ["Noord", "Zuid"],
                "scope": {
                    "enabled": True,
                    "values": ["Noord", "Zuid"],
                    "label": {"nl": "Regio", "en": "Region"},
                    "required_for": ["Members_CRUD"],
                },
            }
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        scope = overlay.fields["region"].scope
        assert scope is not None
        assert scope.enabled is True
        assert tuple(scope.values) == ("Noord", "Zuid")
        assert scope.label == {"nl": "Regio", "en": "Region"}
        assert tuple(scope.required_for) == ("Members_CRUD",)

    def test_get_overlay_fixed_override_carries_scope_attribute(self):
        """A fixed field re-presented as a scope axis carries its scope onto the override."""
        table = FakeTable()
        overrides = {
            "personal.region": {
                "scope": {"enabled": True, "values": ["Noord", "Zuid", "Oost", "West"]}
            }
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        scope = overlay.overrides["personal.region"].scope
        assert scope is not None
        assert scope.enabled is True
        assert tuple(scope.values) == ("Noord", "Zuid", "Oost", "West")

    def test_get_overlay_field_without_scope_attribute_has_none_scope(self):
        """A field with no scope attribute is not a scope axis → scope is None."""
        table = FakeTable()
        fields = {"motor_type": {"key": "motor_type", "type": "string"}}
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert overlay.fields["motor_type"].scope is None

    def test_get_overlay_malformed_scope_attribute_degrades_to_none(self):
        """A non-dict scope attribute degrades to None (projected config data, never raises)."""
        table = FakeTable()
        fields = {"region": {"key": "region", "type": "string", "scope": "not-a-dict"}}
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert overlay.fields["region"].scope is None

    def test_get_overlay_missing_row_returns_empty_overlay(self):
        table = FakeTable()  # nothing seeded
        reader = MembersProjectionReader(table=table)

        overlay = reader.get_overlay("unconfigured")

        assert isinstance(overlay, TenantOverlay)
        assert dict(overlay.fields) == {}
        assert dict(overlay.overrides) == {}


# ---------------------------------------------------------------------------
# Raw config#fields overlay read — the authoring ROUND-TRIP seed (spec 11 bugfix)
#
# get_raw_fields_overlay returns the stored `{fields, overrides, functional_groups}` VERBATIM
# (minus key + version) so the authoring editors LOAD the exact object they PUT back to the SAME
# SAM row — a save is loss-free (GET/PUT symmetric on one table), fixing the "prior selections
# wiped on save" bug. A missing row → clean empty overlay (empty-is-valid), never an error.
# ---------------------------------------------------------------------------


class TestGetRawFieldsOverlay:
    def test_raw_overlay_round_trips_the_stored_slices_verbatim(self):
        table = FakeTable()
        fields = {
            "motor_type": {
                "key": "motor_type",
                "type": "string",
                "application_visible": True,
                "application_required": True,
                "application_choices": ["BMW", "Honda"],
                "format": {"checker": "EMAIL", "params": {"strict": True}},
            }
        }
        overrides = {"personal.city": {"functional_group": "address", "order": 3}}
        item = _config_fields_item("h-dcn", fields, overrides)
        item["functional_groups"] = [
            {"key": "address", "label": {"en": "Address"}, "order": 1}
        ]
        table.put(item)

        reader = MembersProjectionReader(table=table)
        raw = reader.get_raw_fields_overlay("h-dcn")

        # The three slices come back byte-for-byte — incl. the four application attributes the
        # builder authors — so a PUT of this object replaces the row with no loss.
        assert raw["fields"] == fields
        assert raw["overrides"] == overrides
        assert raw["functional_groups"] == [
            {"key": "address", "label": {"en": "Address"}, "order": 1}
        ]
        # No key/version leak into the authoring body.
        assert schema.PARTITION_KEY_ATTR not in raw
        assert schema.SORT_KEY_ATTR not in raw
        assert schema.VERSION_ATTR not in raw

    def test_raw_overlay_missing_row_is_empty_not_an_error(self):
        reader = MembersProjectionReader(table=FakeTable())  # nothing seeded
        raw = reader.get_raw_fields_overlay("unconfigured")
        assert raw == {"fields": {}, "overrides": {}, "functional_groups": []}

    def test_raw_overlay_absent_slices_default_to_empty_containers(self):
        table = FakeTable()
        # A row with only `fields` — overrides / functional_groups absent on the stored item.
        item = {
            schema.PARTITION_KEY_ATTR: "h-dcn",
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, "fields"
            ),
            "fields": {"notes": {"key": "notes", "type": "string"}},
            schema.VERSION_ATTR: 1,
        }
        table.put(item)

        raw = MembersProjectionReader(table=table).get_raw_fields_overlay("h-dcn")
        assert raw["fields"] == {"notes": {"key": "notes", "type": "string"}}
        assert raw["overrides"] == {}
        assert raw["functional_groups"] == []


# ---------------------------------------------------------------------------
# Public member-application attributes on config#fields (task 3.3, seam c)
#
# The four sibling keys a tenant authors per field for the public application form —
# application_visible / application_required / application_choices / format{checker,params} —
# are read back onto the overlay field (OverlayField) and the fixed-field override
# (FixedFieldOverride). `format` DEGRADES to None on an unknown/malformed token (R7.3): a stray
# token never crashes the field-config read, it is simply not enforced.
#
# Validates: Requirements R4.2, R4a, R4b, R7.1, R7.3
# ---------------------------------------------------------------------------


class TestOverlayApplicationAttributes:
    def test_get_overlay_variable_field_carries_the_four_application_attrs(self):
        """A projected overlay field carries all four application attributes 1:1 (D20)."""
        table = FakeTable()
        fields = {
            "motor_type": {
                "key": "motor_type",
                "type": "enum",
                "choices": ["BMW", "Honda", "Yamaha", "Internal"],
                "application_visible": True,
                "application_required": True,
                "application_choices": ["BMW", "Honda", "Yamaha"],
            }
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        field = reader.get_overlay("h-dcn").fields["motor_type"]

        assert field.application_visible is True
        assert field.application_required is True
        assert field.application_choices == ("BMW", "Honda", "Yamaha")

    def test_get_overlay_variable_field_application_attrs_default_off(self):
        """An un-authored overlay field defaults OFF the public form, full choices (back-compat)."""
        table = FakeTable()
        fields = {"motor_type": {"key": "motor_type", "type": "string"}}
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        field = reader.get_overlay("h-dcn").fields["motor_type"]

        assert field.application_visible is False
        assert field.application_required is False
        assert field.application_choices is None
        assert field.format is None

    def test_get_overlay_variable_field_carries_known_format(self):
        """A projected `format` naming a KNOWN token round-trips to FieldFormat (R7.1)."""
        table = FakeTable()
        fields = {
            "contact_email": {
                "key": "contact_email",
                "type": "string",
                "format": {"checker": "EMAIL", "params": {"strict": True}},
            }
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        fmt = reader.get_overlay("h-dcn").fields["contact_email"].format

        assert fmt is not None
        assert fmt.checker == "EMAIL"
        assert dict(fmt.params) == {"strict": True}

    def test_get_overlay_variable_field_unknown_format_token_degrades_to_none(self):
        """An UNKNOWN checker token degrades to None — never raises, never enforced (R7.3)."""
        table = FakeTable()
        fields = {
            "mystery": {
                "key": "mystery",
                "type": "string",
                "format": {"checker": "NOT_A_REAL_CHECKER", "params": {}},
            }
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")  # must not raise

        assert overlay.fields["mystery"].format is None

    def test_get_overlay_variable_field_malformed_format_degrades_to_none(self):
        """A malformed `format` (non-dict / missing checker) degrades to None (R7.3)."""
        table = FakeTable()
        fields = {
            "a": {"key": "a", "type": "string", "format": "EMAIL"},  # not a dict
            "b": {"key": "b", "type": "string", "format": {"params": {}}},  # no checker
            "c": {
                "key": "c",
                "type": "string",
                "format": {"checker": ""},
            },  # empty checker
            "d": {
                "key": "d",
                "type": "string",
                "format": {"checker": 7},
            },  # non-string checker
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")  # must not raise

        assert overlay.fields["a"].format is None
        assert overlay.fields["b"].format is None
        assert overlay.fields["c"].format is None
        assert overlay.fields["d"].format is None

    def test_get_overlay_known_format_non_mapping_params_degrades_to_empty(self):
        """A known token with non-mapping params keeps the checker, drops params to {} (R7.3)."""
        table = FakeTable()
        fields = {
            "iban": {
                "key": "iban",
                "type": "string",
                "format": {"checker": "IBAN", "params": "nonsense"},
            }
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        fmt = reader.get_overlay("h-dcn").fields["iban"].format

        assert fmt is not None
        assert fmt.checker == "IBAN"
        assert dict(fmt.params) == {}

    def test_get_overlay_override_carries_the_four_application_attrs(self):
        """A fixed-field OVERRIDE carries the four application attrs (D20: on overrides too)."""
        table = FakeTable()
        overrides = {
            "membership.membership_type": {
                "application_visible": True,
                "application_required": True,
                "application_choices": ["student", "regular"],
                "format": {"checker": "EMAIL"},
            }
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        ov = reader.get_overlay("h-dcn").overrides["membership.membership_type"]

        assert ov.application_visible is True
        assert ov.application_required is True
        assert ov.application_choices == ("student", "regular")
        assert ov.format is not None
        assert ov.format.checker == "EMAIL"

    def test_get_overlay_override_application_attrs_absent_leave_base_as_is(self):
        """An override touching none of the application attrs leaves them None (base as-is)."""
        table = FakeTable()
        overrides = {"personal.first_name": {"label": {"nl": "Voornaam"}}}
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        ov = reader.get_overlay("h-dcn").overrides["personal.first_name"]

        assert ov.application_visible is None
        assert ov.application_required is None
        assert ov.application_choices is None
        assert ov.format is None

    def test_get_overlay_override_unknown_format_token_degrades_to_none(self):
        """An override's unknown `format` token degrades to None — never raises (R7.3)."""
        table = FakeTable()
        overrides = {
            "membership.membership_type": {
                "format": {"checker": "BOGUS", "params": {}},
            }
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")  # must not raise

        assert overlay.overrides["membership.membership_type"].format is None


# ---------------------------------------------------------------------------
# get_default_page_size — the Phase 2 step (a) pagination default on config#fields
#
# The per-context view_contexts.page_size re-homes to a SINGLE tenant-level
# default_page_size scalar carried on the EXISTING config#fields row (NOT a new
# config#views row). The reader surfaces it so the field-config response can resolve
# rows-per-page as `userPreference ?? default_page_size ?? platformDefault`.
# Empty-is-valid / fail-safe: absent/missing/non-positive/non-int → None.
#
# Validates: Requirements R2.1, R1.2
# ---------------------------------------------------------------------------


def _config_fields_item_with_page_size(tenant_id, page_size, version=1):
    """A config#fields row carrying a default_page_size scalar (empty fields/overrides)."""
    item = _config_fields_item(tenant_id, fields={}, overrides={}, version=version)
    item["default_page_size"] = page_size
    return item


class TestGetDefaultPageSize:
    def test_get_default_page_size_returns_authored_positive_int(self):
        """A projected positive default_page_size is returned verbatim (R2.1)."""
        table = FakeTable()
        table.put(_config_fields_item_with_page_size("h-dcn", 50))

        reader = MembersProjectionReader(table=table)

        assert reader.get_default_page_size("h-dcn") == 50

    def test_get_default_page_size_missing_row_returns_none(self):
        """No config#fields row at all → None (platform fallback), never raises (R2.4)."""
        table = FakeTable()  # nothing seeded

        reader = MembersProjectionReader(table=table)

        assert reader.get_default_page_size("unconfigured") is None

    def test_get_default_page_size_missing_attribute_returns_none(self):
        """A config#fields row without default_page_size → None (today's null-page_size behaviour)."""
        table = FakeTable()
        table.put(_config_fields_item("h-dcn", fields={}, overrides={}))

        reader = MembersProjectionReader(table=table)

        assert reader.get_default_page_size("h-dcn") is None

    def test_get_default_page_size_non_positive_or_malformed_returns_none(self):
        """A non-positive / non-int / boolean value collapses to None (read-side guard, R2.4)."""
        for raw in (0, -10, "25", 3.5, True, False, [], {}, None):
            table = FakeTable()
            table.put(_config_fields_item_with_page_size("h-dcn", raw))
            reader = MembersProjectionReader(table=table)
            assert reader.get_default_page_size("h-dcn") is None, (
                f"raw={raw!r} must resolve to None"
            )

    def test_get_default_page_size_shares_partition_cache_with_other_reads(self):
        """The page-size read shares the per-invocation partition cache (one Query per tenant)."""
        table = FakeTable()
        table.put(_config_fields_item_with_page_size("h-dcn", 25))

        reader = MembersProjectionReader(table=table)
        reader.get_overlay("h-dcn")
        reader.get_default_page_size("h-dcn")

        assert table.query_counts["h-dcn"] == 1

    def test_get_default_page_size_tenant_isolation(self):
        """Each tenant's default answers only from its own partition — no cross-tenant bleed."""
        table = FakeTable()
        table.put(_config_fields_item_with_page_size("tenant-a", 25))
        table.put(_config_fields_item_with_page_size("tenant-b", 100))

        reader = MembersProjectionReader(table=table)

        assert reader.get_default_page_size("tenant-a") == 25
        assert reader.get_default_page_size("tenant-b") == 100


# ---------------------------------------------------------------------------
# get_scope_grants — scopegrant#<email>#<dimension> filtered to the caller
# ---------------------------------------------------------------------------


class TestGetScopeGrants:
    def test_get_scope_grants_returns_dimension_values_for_the_caller(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        assert grants == {"region": ["Noord"]}

    def test_get_scope_grants_all_access_wildcard_preserved(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "admin@example.com", "region", ["*"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "admin@example.com")

        assert grants == {"region": ["*"]}

    def test_get_scope_grants_filtered_to_calling_email(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))
        # A different user's grant in the SAME partition must be excluded.
        table.put(_scopegrant_item("h-dcn", "other@example.com", "region", ["Zuid"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        assert grants == {"region": ["Noord"]}

    def test_get_scope_grants_multiple_dimensions_for_caller(self):
        table = FakeTable()
        table.put(_scopegrant_item("multi", "user@example.com", "region", ["Noord"]))
        table.put(_scopegrant_item("multi", "user@example.com", "season", ["2024"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("multi", "user@example.com")

        assert grants == {"region": ["Noord"], "season": ["2024"]}

    def test_get_scope_grants_missing_grant_is_absent_from_the_map(self):
        table = FakeTable()  # no scopegrant rows for this caller
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        # Deny-by-default is the edge's job (via required_for) — the reader just omits it.
        assert grants == {}
        assert "region" not in grants

    def test_get_scope_grants_missing_partition_returns_empty_map(self):
        reader = MembersProjectionReader(table=FakeTable())
        assert reader.get_scope_grants("nope", "user@example.com") == {}


# ---------------------------------------------------------------------------
# Per-invocation cache — a tenant's partition is Queried at most once
# ---------------------------------------------------------------------------


def test_partition_queried_once_across_all_three_reads():
    """scope config + overlay + grants for the same tenant share ONE Query (cache)."""
    table = FakeTable()
    table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))
    table.put(_config_fields_item("h-dcn", fields={}, overrides={}))
    table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))

    reader = MembersProjectionReader(table=table)

    reader.get_scope_config("h-dcn")
    reader.get_overlay("h-dcn")
    reader.get_scope_grants("h-dcn", "user@example.com")

    # All three method calls hit h-dcn's partition, but the cache means exactly ONE
    # underlying Query was issued for it.
    assert table.query_counts["h-dcn"] == 1


# ---------------------------------------------------------------------------
# Tenant isolation (R7.4) — each partition answers only for its tenant
# ---------------------------------------------------------------------------


def test_scope_and_grants_are_partition_scoped_across_tenants():
    table = FakeTable()
    # Tenant A: region config + a Noord grant for the user.
    table.put(_config_scope_item("tenant-a", [_region_dimension_dict()]))
    table.put(_scopegrant_item("tenant-a", "user@example.com", "region", ["Noord"]))
    # Tenant B: a DIFFERENT config + a Zuid grant for the same user email.
    table.put(
        _config_scope_item("tenant-b", [_region_dimension_dict(values=["A", "B"])])
    )
    table.put(_scopegrant_item("tenant-b", "user@example.com", "region", ["Zuid"]))

    reader = MembersProjectionReader(table=table)

    a_config = reader.get_scope_config("tenant-a")
    a_grants = reader.get_scope_grants("tenant-a", "user@example.com")
    b_config = reader.get_scope_config("tenant-b")
    b_grants = reader.get_scope_grants("tenant-b", "user@example.com")

    # Each tenant's partition answers ONLY for that tenant — no cross-tenant bleed.
    assert tuple(a_config.dimensions[0].values) == ("Noord", "Zuid", "Oost", "West")
    assert a_grants == {"region": ["Noord"]}
    assert tuple(b_config.dimensions[0].values) == ("A", "B")
    assert b_grants == {"region": ["Zuid"]}
    # Exactly one Query per tenant partition.
    assert table.query_counts == {"tenant-a": 1, "tenant-b": 1}


# ═══════════════════════════════════════════════════════════════════════════════════════
# pivot-output-actions Task 0.4 — is_mail_enabled (the config#mail gate row).
#
# Feature: pivot-output-actions, R0 / design §6.3 (the mail-enabled gate, cross-plane READ).
# Validates: Requirements R0
#
# The per-tenant "mail-enabled / SES-certified" flag is authored on the Flask plane and
# projected as a config#mail row. The Members edge resolves the flag from THIS projection
# at request time — NO live MySQL call (ADR 0005/0006). The reader is FAIL-CLOSED: a
# missing row, a missing attribute, or any non-boolean-True value resolves to False.
# ═══════════════════════════════════════════════════════════════════════════════════════


def _config_mail_item(tenant_id, mail_enabled, version=1):
    """A config#mail row (the shape build_config_mail_row produces on the Flask plane)."""
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail"),
        "mail_enabled": mail_enabled,
        schema.VERSION_ATTR: version,
    }


class TestIsMailEnabled:
    def test_is_mail_enabled_true_flag_resolves_true_from_projection(self):
        """An explicit projected mail_enabled=True → the gate is open (R0)."""
        table = FakeTable()
        table.put(_config_mail_item("h-dcn", True))

        assert MembersProjectionReader(table=table).is_mail_enabled("h-dcn") is True

    def test_is_mail_enabled_false_flag_resolves_false(self):
        """A present-but-disabled gate (mail_enabled=False) → the gate is closed."""
        table = FakeTable()
        table.put(_config_mail_item("h-dcn", False))

        assert MembersProjectionReader(table=table).is_mail_enabled("h-dcn") is False

    def test_is_mail_enabled_missing_row_fails_closed_to_false(self):
        """Fail-closed (R0): no config#mail row at all → False, never raises."""
        table = FakeTable()  # nothing seeded for this tenant
        assert (
            MembersProjectionReader(table=table).is_mail_enabled("unconfigured")
            is False
        )

    def test_is_mail_enabled_missing_attribute_fails_closed_to_false(self):
        """A config#mail row with no mail_enabled attribute → False (fail-closed)."""
        table = FakeTable()
        row = _config_mail_item("h-dcn", True)
        del row["mail_enabled"]
        table.put(row)

        assert MembersProjectionReader(table=table).is_mail_enabled("h-dcn") is False

    def test_is_mail_enabled_non_boolean_true_values_fail_closed(self):
        """Any non-boolean-True value never opens the gate (R0): only True enables it."""
        for raw in ("true", "True", 1, "yes", [], {}, None):
            table = FakeTable()
            table.put(_config_mail_item("h-dcn", raw))
            reader = MembersProjectionReader(table=table)
            assert reader.is_mail_enabled("h-dcn") is False, (
                f"raw={raw!r} must fail closed"
            )

    def test_is_mail_enabled_reads_projection_not_mysql(self):
        """The flag resolves purely from the DynamoDB projection — no MySQL seam exists.

        The reader is constructed with ONLY an in-memory projection table (no DB handle,
        no connection); it answers from the seeded config#mail row via a single partition
        Query. This pins the R0 mechanism: the Members edge reads the gate from the
        projection, never a live cross-plane MySQL call.
        """
        table = FakeTable()
        table.put(_config_mail_item("h-dcn", True))

        reader = MembersProjectionReader(table=table)
        result = reader.is_mail_enabled("h-dcn")

        assert result is True
        # Exactly one partition Query answered the gate — the projection is the sole source.
        assert table.query_counts["h-dcn"] == 1

    def test_is_mail_enabled_tenant_isolation(self):
        """Each tenant's gate answers only from its own partition — no cross-tenant bleed."""
        table = FakeTable()
        table.put(_config_mail_item("tenant-a", True))
        table.put(_config_mail_item("tenant-b", False))

        reader = MembersProjectionReader(table=table)

        assert reader.is_mail_enabled("tenant-a") is True
        assert reader.is_mail_enabled("tenant-b") is False
        assert table.query_counts == {"tenant-a": 1, "tenant-b": 1}

    def test_is_mail_enabled_shares_partition_cache_with_other_reads(self):
        """The gate read shares the per-invocation partition cache (one Query per tenant)."""
        table = FakeTable()
        table.put(_config_mail_item("h-dcn", True))
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))

        reader = MembersProjectionReader(table=table)
        reader.get_scope_config("h-dcn")
        reader.is_mail_enabled("h-dcn")

        assert table.query_counts["h-dcn"] == 1


# ═══════════════════════════════════════════════════════════════════════════════════════
# mail spec Task 0.3 — per-tenant sender fields on the config#mail row.
#
# Feature: Members mail (SAM plane), R4/R5 (design Data Models + "Resolved choices" Option B).
# Validates: Requirements R4, R5
#
# The SAME config#mail row that carries mail_enabled now also carries the per-tenant sender
# fields the pre-send resolver (task 1.1) composes From from:
#   From = <mail_local_part|noreply>@<mail_domain>;  the gate reads mail_certified.
# Defaults (design Data Models):
#   - mail_local_part → "noreply" when absent (optional, generic default);
#   - mail_certified  → False (fail-closed) when absent/malformed — identical discipline
#     to is_mail_enabled: only an explicit projected True opens the gate;
#   - mail_domain     → None when absent (NO safe default — a guessed host would be the
#     jabaki.nl foreign-sender regression, R4.2); the resolver refuses when None.
# ═══════════════════════════════════════════════════════════════════════════════════════


def _config_mail_item_full(
    tenant_id,
    *,
    mail_enabled=True,
    version=1,
    **extra,
):
    """A config#mail row carrying the task-0.2-projected sender fields.

    Only the attributes passed in ``extra`` (e.g. ``mail_domain=...``, ``mail_local_part=...``,
    ``mail_certified=...``) are set, so a test can assert the ABSENCE of a field by simply not
    passing it — mirroring how task 0.2's builder omits an unauthored attribute.
    """
    item = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail"),
        "mail_enabled": mail_enabled,
        schema.VERSION_ATTR: version,
    }
    item.update(extra)
    return item


class TestGetMailDomain:
    def test_get_mail_domain_returns_projected_domain(self):
        """A projected mail_domain is returned verbatim (R4)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn", mail_domain="h-dcn.nl"))

        assert (
            MembersProjectionReader(table=table).get_mail_domain("h-dcn") == "h-dcn.nl"
        )

    def test_get_mail_domain_missing_row_returns_none(self):
        """No config#mail row at all → None (no safe default), never raises."""
        table = FakeTable()
        assert (
            MembersProjectionReader(table=table).get_mail_domain("unconfigured") is None
        )

    def test_get_mail_domain_missing_attribute_returns_none(self):
        """A config#mail row without mail_domain → None (resolver refuses, R4.2 guard)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # no mail_domain authored

        assert MembersProjectionReader(table=table).get_mail_domain("h-dcn") is None

    def test_get_mail_domain_empty_or_non_string_returns_none(self):
        """An empty string / non-string value is unusable → None, never a bad From host."""
        for raw in ("", None, 123, [], {}):
            table = FakeTable()
            table.put(_config_mail_item_full("h-dcn", mail_domain=raw))
            reader = MembersProjectionReader(table=table)
            assert reader.get_mail_domain("h-dcn") is None, f"raw={raw!r} must be None"

    def test_get_mail_domain_tenant_isolation(self):
        """Each tenant's domain answers only from its own partition — no cross-tenant bleed."""
        table = FakeTable()
        table.put(_config_mail_item_full("tenant-a", mail_domain="a.example"))
        table.put(_config_mail_item_full("tenant-b", mail_domain="b.example"))

        reader = MembersProjectionReader(table=table)

        assert reader.get_mail_domain("tenant-a") == "a.example"
        assert reader.get_mail_domain("tenant-b") == "b.example"


class TestGetMailLocalPart:
    def test_get_mail_local_part_returns_projected_value(self):
        """A projected mail_local_part is returned verbatim (R4)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn", mail_local_part="info"))

        assert (
            MembersProjectionReader(table=table).get_mail_local_part("h-dcn") == "info"
        )

    def test_get_mail_local_part_missing_row_defaults_to_noreply(self):
        """No config#mail row → the generic default 'noreply' (design Data Models)."""
        table = FakeTable()
        reader = MembersProjectionReader(table=table)
        assert reader.get_mail_local_part("unconfigured") == "noreply"

    def test_get_mail_local_part_missing_attribute_defaults_to_noreply(self):
        """A config#mail row without mail_local_part → 'noreply' (optional field default)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # no mail_local_part authored

        assert (
            MembersProjectionReader(table=table).get_mail_local_part("h-dcn")
            == "noreply"
        )

    def test_get_mail_local_part_empty_or_non_string_defaults_to_noreply(self):
        """An empty / non-string value falls back to the 'noreply' default, never raises."""
        for raw in ("", None, 42, [], {}):
            table = FakeTable()
            table.put(_config_mail_item_full("h-dcn", mail_local_part=raw))
            reader = MembersProjectionReader(table=table)
            assert reader.get_mail_local_part("h-dcn") == "noreply", f"raw={raw!r}"


class TestIsMailCertified:
    def test_is_mail_certified_true_flag_resolves_true(self):
        """An explicit projected mail_certified=True → the gate is open (R5)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn", mail_certified=True))

        assert MembersProjectionReader(table=table).is_mail_certified("h-dcn") is True

    def test_is_mail_certified_false_flag_resolves_false(self):
        """A present-but-false certified flag → the gate is closed."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn", mail_certified=False))

        assert MembersProjectionReader(table=table).is_mail_certified("h-dcn") is False

    def test_is_mail_certified_missing_row_fails_closed_to_false(self):
        """Fail-closed (R5.2): no config#mail row at all → False, never raises."""
        table = FakeTable()
        assert (
            MembersProjectionReader(table=table).is_mail_certified("unconfigured")
            is False
        )

    def test_is_mail_certified_missing_attribute_fails_closed_to_false(self):
        """A config#mail row with no mail_certified attribute → False (fail-closed)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # mail_certified absent

        assert MembersProjectionReader(table=table).is_mail_certified("h-dcn") is False

    def test_is_mail_certified_non_boolean_true_values_fail_closed(self):
        """Any non-boolean-True value never opens the certified gate (Property 4)."""
        for raw in ("true", "True", 1, "yes", [], {}, None):
            table = FakeTable()
            table.put(_config_mail_item_full("h-dcn", mail_certified=raw))
            reader = MembersProjectionReader(table=table)
            assert reader.is_mail_certified("h-dcn") is False, (
                f"raw={raw!r} must fail closed"
            )


class TestSenderFieldsSharePartitionCache:
    def test_all_mail_fields_resolve_from_one_partition_query(self):
        """is_mail_enabled + the three new accessors share the per-invocation cache.

        All four fields live on the SAME config#mail row, so resolving them for one tenant
        issues exactly ONE partition Query (the resolver reads them together at pre-send).
        """
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                mail_enabled=True,
                mail_domain="h-dcn.nl",
                mail_local_part="info",
                mail_certified=True,
            )
        )

        reader = MembersProjectionReader(table=table)
        assert reader.is_mail_enabled("h-dcn") is True
        assert reader.get_mail_domain("h-dcn") == "h-dcn.nl"
        assert reader.get_mail_local_part("h-dcn") == "info"
        assert reader.is_mail_certified("h-dcn") is True

        assert table.query_counts["h-dcn"] == 1


# ═══════════════════════════════════════════════════════════════════════════════════════
# spec 02 Task 5.1/5.2 — get_mail_reply_to_default (the scheduled-send Reply-To default) +
# the config#mail round-trip through the SAM-owned WRITE path (Property 1).
# ═══════════════════════════════════════════════════════════════════════════════════════


class TestGetMailReplyToDefault:
    def test_returns_projected_reply_to_default(self):
        """A projected non-blank mail_reply_to_default is returned verbatim (Task 5.1)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full("h-dcn", mail_reply_to_default="replies@h-dcn.nl")
        )
        assert (
            MembersProjectionReader(table=table).get_mail_reply_to_default("h-dcn")
            == "replies@h-dcn.nl"
        )

    def test_missing_row_returns_none(self):
        """No config#mail row → None (the send path then falls back to the From), never raises."""
        table = FakeTable()
        assert (
            MembersProjectionReader(table=table).get_mail_reply_to_default("x") is None
        )

    def test_missing_attribute_returns_none(self):
        """A config#mail row without mail_reply_to_default → None (From fallback applies)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # no reply-to authored
        assert (
            MembersProjectionReader(table=table).get_mail_reply_to_default("h-dcn")
            is None
        )

    def test_blank_or_non_string_returns_none(self):
        """A blank / non-string value is unusable → None (no fabricated default)."""
        for raw in ("", "   ", None, 123, [], {}):
            table = FakeTable()
            table.put(_config_mail_item_full("h-dcn", mail_reply_to_default=raw))
            reader = MembersProjectionReader(table=table)
            assert reader.get_mail_reply_to_default("h-dcn") is None, f"raw={raw!r}"

    def test_tenant_isolation(self):
        table = FakeTable()
        table.put(
            _config_mail_item_full("tenant-a", mail_reply_to_default="a@x.example")
        )
        table.put(
            _config_mail_item_full("tenant-b", mail_reply_to_default="b@x.example")
        )
        reader = MembersProjectionReader(table=table)
        assert reader.get_mail_reply_to_default("tenant-a") == "a@x.example"
        assert reader.get_mail_reply_to_default("tenant-b") == "b@x.example"


class _WritableFakeTable(FakeTable):
    """A :class:`FakeTable` exposing the boto3 ``put_item`` the write repository calls, so the
    SAME in-memory store is written by ``MembersConfigWriteRepository`` and read by the reader —
    a real config#mail write→read round-trip with no live AWS (Property 1)."""

    def put_item(self, Item):
        self.put(Item)


class TestConfigMailWriteReadRoundTrip:
    """Property 1 (config#mail): put_config('mail', {...}) → the reader's mail accessors return
    equivalent values; fail-closed gate + no-safe-default domain hold across the round-trip."""

    def _round_trip(self, attributes):
        from sam.members.domain.config_write_version import next_write_stamp
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )

        table = _WritableFakeTable()
        MembersConfigWriteRepository(table=table).put_config(
            tenant_id="h-dcn",
            config_id=schema.CONFIG_ID_MAIL,
            attributes=attributes,
            version=next_write_stamp(),
        )
        return MembersProjectionReader(table=table)

    def test_full_mail_row_round_trips_through_the_accessors(self):
        reader = self._round_trip(
            {
                "mail_enabled": True,
                "mail_certified": True,
                "mail_domain": "h-dcn.nl",
                "mail_local_part": "info",
                "mail_reply_to_default": "replies@h-dcn.nl",
            }
        )
        assert reader.is_mail_enabled("h-dcn") is True
        assert reader.is_mail_certified("h-dcn") is True
        assert reader.get_mail_domain("h-dcn") == "h-dcn.nl"
        assert reader.get_mail_local_part("h-dcn") == "info"
        assert reader.get_mail_reply_to_default("h-dcn") == "replies@h-dcn.nl"

    def test_empty_mail_row_is_fail_closed_across_the_round_trip(self):
        # An empty authored body: gates fail-closed, local-part defaults, no domain/reply-to.
        reader = self._round_trip({"mail_enabled": False, "mail_certified": False})
        assert reader.is_mail_enabled("h-dcn") is False
        assert reader.is_mail_certified("h-dcn") is False
        assert reader.get_mail_domain("h-dcn") is None  # no safe default (R4.2)
        assert reader.get_mail_local_part("h-dcn") == "noreply"
        assert (
            reader.get_mail_reply_to_default("h-dcn") is None
        )  # From fallback applies


# ═══════════════════════════════════════════════════════════════════════════════════════
# application-form-builder Task 5.3 — get_application_embed_origins: the SAM read side of the
# ONE tenant-authored embed-origin list on config#mail (authored by task 5.1's _shape_embed_
# origins). It feeds BOTH the CloudFront form `frame-ancestors` (task 5.2) and the SAM public
# API CORS `Access-Control-Allow-Origin` (task 5.3, consumed by public_app._tenant_embed_origins).
# Same read discipline as the sibling config#mail accessors: one partition Query (shared cache),
# empty-is-valid / fail-safe (→ [], never raises), trim + de-dupe belt-and-suspenders.
# ═══════════════════════════════════════════════════════════════════════════════════════


class TestGetApplicationEmbedOrigins:
    def test_returns_projected_origins_verbatim(self):
        """A projected list of origins is returned (already shaped by the write path)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                application_embed_origins=[
                    "https://members.h-dcn.nl",
                    "https://aanmelden.h-dcn.nl",
                ],
            )
        )
        assert MembersProjectionReader(table=table).get_application_embed_origins(
            "h-dcn"
        ) == ["https://members.h-dcn.nl", "https://aanmelden.h-dcn.nl"]

    def test_missing_row_fails_safe_to_empty_list(self):
        """No config#mail row at all → [] (standalone, no cross-origin embed), never raises."""
        table = FakeTable()  # nothing seeded
        assert (
            MembersProjectionReader(table=table).get_application_embed_origins(
                "unconfigured"
            )
            == []
        )

    def test_missing_attribute_fails_safe_to_empty_list(self):
        """A config#mail row without the attribute → [] (an un-authored tenant is standalone)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # no embed origins authored
        assert (
            MembersProjectionReader(table=table).get_application_embed_origins("h-dcn")
            == []
        )

    def test_non_list_values_fail_safe_to_empty_list(self):
        """A non-list stored value (hand-edited / legacy) degrades to [] — never raises."""
        for raw in ("https://x.example", None, 123, {}):
            table = FakeTable()
            table.put(_config_mail_item_full("h-dcn", application_embed_origins=raw))
            reader = MembersProjectionReader(table=table)
            assert reader.get_application_embed_origins("h-dcn") == [], f"raw={raw!r}"

    def test_blank_and_non_string_entries_are_dropped(self):
        """Belt-and-suspenders read guard: blank/non-string entries are skipped (not raised)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                application_embed_origins=[
                    "  https://members.h-dcn.nl  ",  # trimmed
                    "   ",  # blank → dropped
                    42,  # non-string → dropped
                    "https://members.h-dcn.nl",  # duplicate of the trimmed entry → de-duped
                ],
            )
        )
        assert MembersProjectionReader(table=table).get_application_embed_origins(
            "h-dcn"
        ) == ["https://members.h-dcn.nl"]

    def test_tenant_isolation(self):
        """Each tenant's embed origins answer only from its own partition — no bleed."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "tenant-a", application_embed_origins=["https://a.example"]
            )
        )
        table.put(
            _config_mail_item_full(
                "tenant-b", application_embed_origins=["https://b.example"]
            )
        )
        reader = MembersProjectionReader(table=table)
        assert reader.get_application_embed_origins("tenant-a") == ["https://a.example"]
        assert reader.get_application_embed_origins("tenant-b") == ["https://b.example"]

    def test_shares_partition_cache_with_sibling_mail_accessors(self):
        """The embed-origins read shares the per-invocation partition cache (one Query)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                mail_domain="h-dcn.nl",
                application_embed_origins=["https://members.h-dcn.nl"],
            )
        )
        reader = MembersProjectionReader(table=table)
        reader.get_mail_domain("h-dcn")
        reader.get_application_embed_origins("h-dcn")
        assert table.query_counts["h-dcn"] == 1

    def test_round_trips_through_the_sam_owned_write_path(self):
        """Property 1: put_config('mail', {application_embed_origins: [...]}) → reader returns it."""
        from sam.members.domain.config_write_version import next_write_stamp
        from sam.members.repository.projection_config_write_repository import (
            MembersConfigWriteRepository,
        )

        table = _WritableFakeTable()
        MembersConfigWriteRepository(table=table).put_config(
            tenant_id="h-dcn",
            config_id=schema.CONFIG_ID_MAIL,
            attributes={
                "mail_enabled": True,
                "application_embed_origins": ["https://members.h-dcn.nl"],
            },
            version=next_write_stamp(),
        )
        assert MembersProjectionReader(table=table).get_application_embed_origins(
            "h-dcn"
        ) == ["https://members.h-dcn.nl"]


# ---------------------------------------------------------------------------
# get_config_status — delivered/loaded projection status (Phase 0 step 3)
# ---------------------------------------------------------------------------


class TestGetConfigStatus:
    def test_get_config_status_reports_delivered_row_versions(self):
        """A present config#* row surfaces its projected version (delivered + loaded)."""
        table = FakeTable()
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()], version=5))
        table.put(
            _config_fields_item(
                "h-dcn", fields={}, overrides={}, version="2026-10-12T09:00:00"
            )
        )

        status = MembersProjectionReader(table=table).get_config_status("h-dcn")

        assert status["scope"] == 5
        assert status["fields"] == "2026-10-12T09:00:00"
        # mail was never delivered for this tenant → None. Phase 2 (R5.3/R5.5) retired the
        # config#views row, so the status map no longer carries a "views" key.
        assert status["mail"] is None
        assert "views" not in status

    def test_get_config_status_all_absent_is_all_none(self):
        """A tenant with no projection at all → every config id maps to None (empty-is-valid)."""
        table = FakeTable()  # nothing seeded

        status = MembersProjectionReader(table=table).get_config_status("unconfigured")

        # Phase 2 (R5.3/R5.5): no "views" key — the config#views row was retired.
        assert status == {"scope": None, "fields": None, "mail": None}

    def test_get_config_status_shares_partition_cache(self):
        """All config rows resolve from ONE partition Query (per-invocation cache)."""
        table = FakeTable()
        table.put(_config_scope_item("h-dcn", [], version=1))
        table.put(_config_fields_item("h-dcn", fields={}, overrides={}, version=1))

        reader = MembersProjectionReader(table=table)
        reader.get_config_status("h-dcn")

        assert table.query_counts["h-dcn"] == 1

    def test_get_config_status_is_tenant_isolated(self):
        """Only the queried tenant's versions are reported — no cross-tenant bleed."""
        table = FakeTable()
        table.put(_config_scope_item("tenant-a", [], version=9))
        table.put(_config_scope_item("tenant-b", [], version=3))

        status_a = MembersProjectionReader(table=table).get_config_status("tenant-a")

        assert status_a["scope"] == 9


# ═══════════════════════════════════════════════════════════════════════════════════════
# spec 02 task 7.1 fix — get_mail_config: the full reader-shaped config#mail body the typed
# Mail authoring form loads from (surfaced on GET /members/field-config as `mail_config`).
# ═══════════════════════════════════════════════════════════════════════════════════════


class TestGetMailConfig:
    def test_full_authored_body_round_trips(self):
        """Every authored mail scalar composes into the reader-shaped body (writer/reader parity)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                mail_enabled=True,
                mail_local_part="info",
                mail_certified=True,
                mail_domain="h-dcn.nl",
                mail_reply_to_default="webmaster@h-dcn.nl",
                consent_notice={"version": "2026-01", "text": {"nl": "Tekst"}},
            )
        )
        body = MembersProjectionReader(table=table).get_mail_config("h-dcn")
        assert body == {
            "mail_enabled": True,
            "mail_local_part": "info",
            "mail_certified": True,
            "mail_domain": "h-dcn.nl",
            "mail_reply_to_default": "webmaster@h-dcn.nl",
            "consent_notice": {"version": "2026-01", "text": {"nl": "Tekst"}},
        }

    def test_missing_row_yields_fail_closed_minimal_body(self):
        """No config#mail row → the safe minimal body (not-enabled, noreply, not-certified)."""
        table = FakeTable()  # nothing seeded
        body = MembersProjectionReader(table=table).get_mail_config("unconfigured")
        assert body == {
            "mail_enabled": False,
            "mail_local_part": "noreply",
            "mail_certified": False,
        }
        # The optional attributes are OMITTED, not present-and-null.
        assert "mail_domain" not in body
        assert "mail_reply_to_default" not in body
        assert "consent_notice" not in body

    def test_optional_fields_omitted_when_unauthored(self):
        """A minimal authored row surfaces only the always-present trio; options omitted."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn", mail_enabled=True))
        body = MembersProjectionReader(table=table).get_mail_config("h-dcn")
        assert body["mail_enabled"] is True
        assert body["mail_local_part"] == "noreply"
        assert body["mail_certified"] is False
        assert "mail_domain" not in body
        assert "mail_reply_to_default" not in body
        assert "consent_notice" not in body

    def test_reply_to_default_round_trips(self):
        """The SAM-only mail_reply_to_default (the reported bug's field) reads back verbatim."""
        table = FakeTable()
        table.put(
            _config_mail_item_full("h-dcn", mail_reply_to_default="webmaster@h-dcn.nl")
        )
        body = MembersProjectionReader(table=table).get_mail_config("h-dcn")
        assert body["mail_reply_to_default"] == "webmaster@h-dcn.nl"

    def test_mail_config_shares_partition_cache(self):
        """The composed body resolves from ONE partition Query (all accessors share the cache)."""
        table = FakeTable()
        table.put(
            _config_mail_item_full(
                "h-dcn",
                mail_enabled=True,
                mail_domain="h-dcn.nl",
                mail_reply_to_default="replies@h-dcn.nl",
            )
        )
        reader = MembersProjectionReader(table=table)
        reader.get_mail_config("h-dcn")
        assert table.query_counts["h-dcn"] == 1

    def test_mail_config_tenant_isolation(self):
        """Each tenant's body answers only from its own partition — no cross-tenant bleed."""
        table = FakeTable()
        table.put(_config_mail_item_full("tenant-a", mail_domain="a.example"))
        table.put(_config_mail_item_full("tenant-b", mail_domain="b.example"))
        reader = MembersProjectionReader(table=table)
        assert reader.get_mail_config("tenant-a")["mail_domain"] == "a.example"
        assert reader.get_mail_config("tenant-b")["mail_domain"] == "b.example"
