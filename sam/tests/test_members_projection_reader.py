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
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_projection_governance_reader.py — the projection schema is the single source of truth
# for the key shape, shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.field_resolver import AnalyticsRole, TenantOverlay
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.domain.view_contexts import DEFAULT_CONTEXT_KEY, ViewContext
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
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
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
            _config_scope_item("h-dcn", [_region_dimension_dict(enabled=False, values=[])])
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

    def test_get_overlay_missing_row_returns_empty_overlay(self):
        table = FakeTable()  # nothing seeded
        reader = MembersProjectionReader(table=table)

        overlay = reader.get_overlay("unconfigured")

        assert isinstance(overlay, TenantOverlay)
        assert dict(overlay.fields) == {}
        assert dict(overlay.overrides) == {}
        # member-analytics R9: no analytics slice authored → None (empty-is-valid, R9.5).
        assert overlay.analytics is None


# ---------------------------------------------------------------------------
# member-analytics (R9, C-CONFIG) — the analytics slice on config#fields → TenantOverlay.analytics
#
# ODI-2: the analytics config rides on the SAME config#fields row (an `analytics` object), so the
# reader rebuilds it onto TenantOverlay.analytics. Empty-is-valid: an absent/empty slice → None.
#
# Validates: Requirements R9.1, R9.5
# ---------------------------------------------------------------------------


def _config_fields_item_with_analytics(tenant_id, analytics, version=1):
    item = _config_fields_item(tenant_id, fields={}, overrides={}, version=version)
    item["analytics"] = analytics
    return item


class TestGetOverlayAnalytics:
    def test_analytics_slice_round_trips_all_three_blocks(self):
        table = FakeTable()
        table.put(
            _config_fields_item_with_analytics(
                "h-dcn",
                {
                    "jubilee_rule": {"years": [25, 40, 50]},
                    "field_roles": {
                        "cancellation_date": "overlay.opzegdatum",
                        "clubblad_paper": "overlay.clubblad_papier",
                    },
                    "address_mapping": {
                        "name": "personal.display_name",
                        "street": "overlay.straat",
                        "postcode": "overlay.postcode",
                        "city": "overlay.woonplaats",
                    },
                },
            )
        )
        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        analytics = overlay.analytics
        assert analytics is not None
        assert analytics.jubilee_rule is not None
        assert analytics.jubilee_rule.years == (25, 40, 50)
        assert analytics.jubilee_rule.multiple_of is None
        assert analytics.field_roles[AnalyticsRole.CANCELLATION_DATE] == "overlay.opzegdatum"
        assert analytics.field_roles[AnalyticsRole.CLUBBLAD_PAPER] == "overlay.clubblad_papier"
        assert analytics.address_mapping is not None
        assert analytics.address_mapping.name == "personal.display_name"
        assert analytics.address_mapping.street == "overlay.straat"
        assert analytics.address_mapping.country is None  # absent line stays None

    def test_jubilee_multiple_of_rule_round_trips(self):
        table = FakeTable()
        table.put(
            _config_fields_item_with_analytics(
                "h-dcn", {"jubilee_rule": {"multiple_of": 5}}
            )
        )
        reader = MembersProjectionReader(table=table)
        rule = reader.get_overlay("h-dcn").analytics.jubilee_rule
        assert rule is not None
        assert rule.multiple_of == 5
        assert rule.years is None

    def test_unknown_role_token_is_skipped_not_raised(self):
        table = FakeTable()
        table.put(
            _config_fields_item_with_analytics(
                "h-dcn",
                {"field_roles": {"not_a_real_role": "overlay.x", "referral_source": "overlay.bron"}},
            )
        )
        reader = MembersProjectionReader(table=table)
        roles = reader.get_overlay("h-dcn").analytics.field_roles
        # The stray token degrades gracefully (skipped); the valid role survives.
        assert roles == {AnalyticsRole.REFERRAL_SOURCE: "overlay.bron"}

    def test_empty_analytics_slice_collapses_to_none(self):
        table = FakeTable()
        table.put(
            _config_fields_item_with_analytics(
                "h-dcn",
                {"jubilee_rule": {}, "field_roles": {}, "address_mapping": {}},
            )
        )
        reader = MembersProjectionReader(table=table)
        assert reader.get_overlay("h-dcn").analytics is None

    def test_non_dict_analytics_slice_collapses_to_none(self):
        table = FakeTable()
        table.put(_config_fields_item_with_analytics("h-dcn", "not-a-dict"))
        reader = MembersProjectionReader(table=table)
        assert reader.get_overlay("h-dcn").analytics is None


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
# S5c Task 3.1 — get_view_contexts (the sibling config#views row).
#
# Feature: s5c-members-runnable-in-spa, C-VIEW.
# Validates: Requirements 5.1
#
# The reader consumes the SETTLED projection shape (Open Design Item 1): a sibling config#views
# row carrying a `contexts` list. Empty/absent → EXACTLY ONE default context (empty-is-valid),
# over all visible fields (empty columns = the "all visible fields" sentinel).
# ═══════════════════════════════════════════════════════════════════════════════════════


def _config_views_item(tenant_id, contexts, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "views"),
        "contexts": contexts,
        schema.VERSION_ATTR: version,
    }


def _overview_context_dict():
    return {
        "key": "overview",
        "label": {"nl": "Overzicht", "en": "Overview"},
        "permission_roles": ["Members_Read", "Members_CRUD"],
        "columns": ["member_number", "email", "status"],
        "filterable_columns": ["status"],
        "default_sort": {"field": "member_number", "direction": "asc"},
        "page_size": 50,
    }


class TestGetViewContexts:
    def test_get_view_contexts_round_trips_authored_contexts(self):
        table = FakeTable()
        financial = {
            "key": "financial",
            "label": {"en": "Financial"},
            "permission_roles": ["Members_CRUD"],
            "columns": ["member_number", "iban"],
            "filterable_columns": [],
            "default_sort": None,
            "page_size": 25,
        }
        table.put(_config_views_item("h-dcn", [_overview_context_dict(), financial]))

        contexts = MembersProjectionReader(table=table).get_view_contexts("h-dcn")

        assert all(isinstance(c, ViewContext) for c in contexts)
        assert [c.key for c in contexts] == ["overview", "financial"]
        overview = contexts[0]
        assert overview.label == {"nl": "Overzicht", "en": "Overview"}
        assert tuple(overview.permission_roles) == ("Members_Read", "Members_CRUD")
        assert tuple(overview.columns) == ("member_number", "email", "status")
        assert tuple(overview.filterable_columns) == ("status",)
        assert overview.default_sort == {"field": "member_number", "direction": "asc"}
        assert overview.page_size == 50
        assert contexts[1].page_size == 25
        assert contexts[1].default_sort is None

    def test_get_view_contexts_missing_row_collapses_to_one_default_context(self):
        # No config#views row at all → exactly one default context (empty-is-valid, R5.1).
        table = FakeTable()
        table.put(_config_scope_item("h-dcn", []))  # some other row present, but no views row

        contexts = MembersProjectionReader(table=table).get_view_contexts("h-dcn")

        assert len(contexts) == 1
        ctx = contexts[0]
        assert ctx.key == DEFAULT_CONTEXT_KEY
        assert ctx.is_default is True
        # Over all visible fields: empty columns = the "all visible fields" sentinel.
        assert tuple(ctx.columns) == ()
        assert tuple(ctx.filterable_columns) == ()

    def test_get_view_contexts_empty_contexts_list_collapses_to_one_default(self):
        # A present config#views row with an EMPTY contexts list → one default context.
        table = FakeTable()
        table.put(_config_views_item("h-dcn", []))

        contexts = MembersProjectionReader(table=table).get_view_contexts("h-dcn")

        assert len(contexts) == 1
        assert contexts[0].key == DEFAULT_CONTEXT_KEY

    def test_get_view_contexts_all_malformed_contexts_collapse_to_one_default(self):
        # Every entry malformed (non-dict / no key) → skipped → one default context.
        table = FakeTable()
        table.put(_config_views_item("h-dcn", ["nope", {"no_key": 1}, 42]))

        contexts = MembersProjectionReader(table=table).get_view_contexts("h-dcn")

        assert len(contexts) == 1
        assert contexts[0].key == DEFAULT_CONTEXT_KEY

    def test_get_view_contexts_skips_malformed_but_keeps_well_formed(self):
        table = FakeTable()
        table.put(
            _config_views_item("h-dcn", [{"no_key": 1}, _overview_context_dict()])
        )

        contexts = MembersProjectionReader(table=table).get_view_contexts("h-dcn")

        assert [c.key for c in contexts] == ["overview"]

    def test_get_view_contexts_degrades_malformed_subvalues(self):
        # Non-list columns / non-mapping default_sort / non-int page_size degrade gracefully.
        table = FakeTable()
        table.put(
            _config_views_item(
                "h-dcn",
                [
                    {
                        "key": "overview",
                        "columns": "not-a-list",
                        "filterable_columns": None,
                        "default_sort": "not-a-map",
                        "page_size": "50",
                    }
                ],
            )
        )

        ctx = MembersProjectionReader(table=table).get_view_contexts("h-dcn")[0]

        assert ctx.key == "overview"
        assert tuple(ctx.columns) == ()
        assert tuple(ctx.filterable_columns) == ()
        assert ctx.default_sort is None
        assert ctx.page_size is None

    def test_get_view_contexts_tenant_isolation(self):
        table = FakeTable()
        table.put(_config_views_item("tenant-a", [_overview_context_dict()]))
        # tenant-b has no views row.

        reader = MembersProjectionReader(table=table)
        a = reader.get_view_contexts("tenant-a")
        b = reader.get_view_contexts("tenant-b")

        assert [c.key for c in a] == ["overview"]
        assert [c.key for c in b] == [DEFAULT_CONTEXT_KEY]


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
        assert MembersProjectionReader(table=table).is_mail_enabled("unconfigured") is False

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
            assert reader.is_mail_enabled("h-dcn") is False, f"raw={raw!r} must fail closed"

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

        assert MembersProjectionReader(table=table).get_mail_domain("h-dcn") == "h-dcn.nl"

    def test_get_mail_domain_missing_row_returns_none(self):
        """No config#mail row at all → None (no safe default), never raises."""
        table = FakeTable()
        assert MembersProjectionReader(table=table).get_mail_domain("unconfigured") is None

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

        assert MembersProjectionReader(table=table).get_mail_local_part("h-dcn") == "info"

    def test_get_mail_local_part_missing_row_defaults_to_noreply(self):
        """No config#mail row → the generic default 'noreply' (design Data Models)."""
        table = FakeTable()
        reader = MembersProjectionReader(table=table)
        assert reader.get_mail_local_part("unconfigured") == "noreply"

    def test_get_mail_local_part_missing_attribute_defaults_to_noreply(self):
        """A config#mail row without mail_local_part → 'noreply' (optional field default)."""
        table = FakeTable()
        table.put(_config_mail_item_full("h-dcn"))  # no mail_local_part authored

        assert MembersProjectionReader(table=table).get_mail_local_part("h-dcn") == "noreply"

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
        assert MembersProjectionReader(table=table).is_mail_certified("unconfigured") is False

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
            assert reader.is_mail_certified("h-dcn") is False, f"raw={raw!r} must fail closed"


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
