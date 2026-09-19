"""
S5b Task 8.4 — property-based **empty-is-valid collapse** tests (design Correctness Properties).

Feature: s5b-members-runnable-in-spa, Property 3: Empty-is-valid collapses to tenant-wide /
fixed base.

Validates: Requirements 1.6, 1.7, 10.2, 10.6

What this asserts (the FULL empty-is-valid collapse, via the reader)
--------------------------------------------------------------------
Property 3 (design Correctness Properties): "For all tenants with no ``config#scope`` row, the
reader yields a tenant-wide ``ScopeConfig`` (empty dimensions, so ``resolve_scope_access``
returns ``["*"]``); and for all tenants with no ``config#fields`` row, the reader yields the
fixed-field base — in both cases without raising."

Two properties, each ≥100 generated iterations (``@settings(max_examples=100)``):

- ``test_property_no_config_scope_collapses_to_tenant_wide`` (R1.6): for ANY tenant partition
  that contains NO ``config#scope`` row (a completely empty partition, or one carrying only
  OTHER rows — ``tenant`` / ``module#…`` / ``role#…`` / ``scopegrant#…`` — but never a
  ``config#scope``), ``reader.get_scope_config(tid)`` returns a ``ScopeConfig`` with EMPTY
  dimensions, ``is_tenant_wide() is True``, and never raises; AND the domain
  ``resolve_scope_access(tid, None, <any roles>)`` collapses to ``allowed_scopes == ["*"]``
  (the tenant-wide collapse — asserted end-to-end, not merely "no raise").
- ``test_property_no_config_fields_yields_fixed_base`` (R1.7): for ANY tenant partition that
  contains NO ``config#fields`` row, ``reader.get_overlay(tid)`` returns an EMPTY
  ``TenantOverlay`` and never raises; AND feeding that overlay through
  ``FieldResolver(reader).resolve(tid)`` (the reader IS a ``TenantOverlayProvider``) yields
  EXACTLY the platform fixed base — one resolved field per :data:`FIXED_FIELDS`, all
  ``FieldOrigin.FIXED``, no ``VARIABLE`` field, and each fixed field's base
  label/required/order/visible unchanged (asserted concretely, not merely "no raise").

Genuine (non-tautological) collapse
------------------------------------
The strategies GENERATE arbitrary "noise" partitions — any mix of ``tenant`` / ``module#…`` /
``role#…`` / ``scopegrant#…`` rows plus the empty-partition case — but are constrained to NEVER
emit the row under test (``config#scope`` for the scope property, ``config#fields`` for the
overlay property). The scope property may still include a ``config#fields`` row and vice-versa,
so "no scope row" is proved in the presence of arbitrary other rows (including the *other*
config row), not only on an empty partition. The assertions then pin the collapse to a concrete
target — tenant-wide ``["*"]`` for scope; the exact fixed base for fields — so the test is a
real proof of Property 3, not "does not raise".

No live AWS, no MySQL: the reader queries an in-memory ``FakeTable`` (mirrors
``sam/tests/test_members_projection_reader.py`` / ``sam/tests/test_config_roundtrip_props.py``).
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_members_projection_reader.py — the projection schema is shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.field_resolver import (
    FieldOrigin,
    FieldResolver,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FIXED_FIELDS
from sam.members.domain.scope_access import resolve_scope_access
from sam.members.domain.scope_dimensions import WILDCARD, ScopeConfig
from sam.members.repository.projection_config_reader import MembersProjectionReader


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (query side only) — mirrors the example tests
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side).

    ``query(KeyConditionExpression=...)`` returns ONLY the seeded items whose partition key
    matches the boto3 ``Key(...).eq(...)`` condition (cross-tenant items never returned).
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = KeyConditionExpression.get_expression()["values"][1]
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


# ---------------------------------------------------------------------------
# Row builders (canonical schema keys so SKs match production) — mirror the
# reader test's `_config_*` / `_scopegrant_*` helpers, plus tenant/module/role.
# ---------------------------------------------------------------------------


def _tenant_item(tenant_id, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_TENANT),
        schema.VERSION_ATTR: version,
    }


def _module_item(tenant_id, module, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_MODULE, module),
        schema.VERSION_ATTR: version,
    }


def _role_item(tenant_id, email, role, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_ROLE, email, role),
        schema.VERSION_ATTR: version,
    }


def _scopegrant_item(tenant_id, email, dimension, values, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_SCOPEGRANT, email, dimension
        ),
        "dimension": dimension,
        "values": list(values),
        schema.VERSION_ATTR: version,
    }


def _config_fields_item(tenant_id, fields=None, overrides=None, version=1):
    """A ``config#fields`` row — allowed as NOISE for the scope property (never for fields)."""
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "fields": fields or {},
        "overrides": overrides or {},
        schema.VERSION_ATTR: version,
    }


def _config_scope_item(tenant_id, dimensions=None, version=1):
    """A ``config#scope`` row — allowed as NOISE for the fields property (never for scope)."""
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
        "dimensions": dimensions or [],
        schema.VERSION_ATTR: version,
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A non-blank identifier token (tenant ids, module names, role names, emails' local part).
_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)

# A tenant id: non-blank (the reader/ScopeConfig require it) and free of the SK separator so
# it can never be confused with a composite key.
_TENANT_ID = _TOKEN.filter(lambda t: schema.SORT_KEY_SEPARATOR not in t)

# An email-shaped token (the segment scopegrant#<email>#… / role#<email>#… key on). Kept free
# of the SK separator so the composite key stays well-formed.
_EMAIL = st.builds(lambda a, b: f"{a}@{b}.com", _TOKEN, _TOKEN)

# Arbitrary roles the caller might carry — resolve_scope_access must still collapse to ["*"]
# for a None (tenant-wide) dimension regardless of these (incl. admin/scoped-looking names).
_ROLES = st.lists(
    st.one_of(
        _TOKEN,
        st.sampled_from(
            ["Members_CRUD", "Regio_Noord", "Regio_All", "SystemAdmin", "TenantAdmin"]
        ),
    ),
    max_size=6,
)


@st.composite
def _noise_rows(draw, tenant_id, *, allow_config_scope, allow_config_fields):
    """A list of arbitrary NON-target rows for ``tenant_id`` (possibly empty).

    Any mix of ``tenant`` / ``module#…`` / ``role#…`` / ``scopegrant#…`` rows. The two config
    rows are gated: for the SCOPE property we allow a ``config#fields`` noise row (never
    ``config#scope``); for the FIELDS property we allow a ``config#scope`` noise row (never
    ``config#fields``). This proves the collapse in the presence of the *other* config row too,
    not just on an empty partition.
    """
    builders = []

    if draw(st.booleans()):
        builders.append(_tenant_item(tenant_id))

    for module in draw(st.lists(_TOKEN, max_size=3, unique=True)):
        builders.append(_module_item(tenant_id, module))

    for email, role in draw(
        st.lists(st.tuples(_EMAIL, _TOKEN), max_size=3, unique_by=lambda er: (er[0], er[1]))
    ):
        builders.append(_role_item(tenant_id, email, role))

    for email, dim, vals in draw(
        st.lists(
            st.tuples(
                _EMAIL,
                _TOKEN,
                st.one_of(
                    st.just(["*"]),
                    st.lists(_TOKEN, min_size=1, max_size=3, unique=True),
                ),
            ),
            max_size=3,
            unique_by=lambda t: (t[0], t[1]),
        )
    ):
        builders.append(_scopegrant_item(tenant_id, email, dim, vals))

    if allow_config_fields and draw(st.booleans()):
        builders.append(_config_fields_item(tenant_id))

    if allow_config_scope and draw(st.booleans()):
        builders.append(_config_scope_item(tenant_id))

    return builders


def _seed(tenant_id, rows):
    table = FakeTable()
    for row in rows:
        table.put(row)
    return table


def _has_config_row(table, tenant_id, config_id):
    """Whether the seeded partition actually contains a ``config#<config_id>`` row (guard)."""
    target = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id)
    return (tenant_id, target) in table.store


# ---------------------------------------------------------------------------
# Property 3a — no config#scope → tenant-wide ["*"] (R1.6)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data(), tenant_id=_TENANT_ID, roles=_ROLES)
def test_property_no_config_scope_collapses_to_tenant_wide(data, tenant_id, roles):
    """Feature: s5b-members-runnable-in-spa, Property 3: Empty-is-valid collapses to tenant-wide / fixed base.

    Validates: Requirements 1.6, 1.7, 10.2, 10.6

    For ANY partition with NO ``config#scope`` row (empty, or carrying only other rows —
    including a ``config#fields`` row), the reader yields an empty tenant-wide ``ScopeConfig``
    without raising, and the domain collapses to ``allowed_scopes == ["*"]``.
    """
    rows = data.draw(
        _noise_rows(tenant_id, allow_config_scope=False, allow_config_fields=True)
    )
    table = _seed(tenant_id, rows)
    # Guard: the generator must never have emitted the target row (proves genuine "no scope").
    assert not _has_config_row(table, tenant_id, "scope")

    reader = MembersProjectionReader(table=table)

    # Reader yields an empty, tenant-wide ScopeConfig — and never raises.
    config = reader.get_scope_config(tenant_id)
    assert isinstance(config, ScopeConfig)
    assert config.tenant_id == tenant_id
    assert config.dimensions == ()
    assert config.is_tenant_wide() is True

    # The collapse end-to-end: no config#scope → tenant-wide ["*"] for arbitrary roles.
    access = resolve_scope_access(tenant_id, None, roles)
    assert access.allowed_scopes == [WILDCARD]
    assert access.allowed_scopes == ["*"]
    assert access.full_access is True


# ---------------------------------------------------------------------------
# Property 3b — no config#fields → the fixed-field base (R1.7)
# ---------------------------------------------------------------------------

# The exact fixed base each resolved fixed field must reproduce (label/required/order/visible).
_EXPECTED_FIXED = {
    f.dotted_key(): {
        "key": f.key,
        "group": f.group.value,
        "type": f.type,
        "required": f.required,
        "label": dict(f.label),
        "choices": tuple(f.choices) if f.choices is not None else None,
        "order": f.order,
        "visible": True,  # no overlay → the base default (nothing hides a fixed field)
    }
    for f in FIXED_FIELDS
}


@settings(max_examples=100)
@given(data=st.data(), tenant_id=_TENANT_ID)
def test_property_no_config_fields_yields_fixed_base(data, tenant_id):
    """Feature: s5b-members-runnable-in-spa, Property 3: Empty-is-valid collapses to tenant-wide / fixed base.

    Validates: Requirements 1.6, 1.7, 10.2, 10.6

    For ANY partition with NO ``config#fields`` row (empty, or carrying only other rows —
    including a ``config#scope`` row), the reader yields an EMPTY ``TenantOverlay`` without
    raising, and ``FieldResolver(reader).resolve(tid)`` yields EXACTLY the platform fixed base.
    """
    rows = data.draw(
        _noise_rows(tenant_id, allow_config_scope=True, allow_config_fields=False)
    )
    table = _seed(tenant_id, rows)
    # Guard: the generator must never have emitted the target row (proves genuine "no fields").
    assert not _has_config_row(table, tenant_id, "fields")

    reader = MembersProjectionReader(table=table)

    # Reader yields an empty overlay — and never raises.
    overlay = reader.get_overlay(tenant_id)
    assert isinstance(overlay, TenantOverlay)
    assert dict(overlay.fields) == {}
    assert dict(overlay.overrides) == {}

    # The collapse end-to-end: empty overlay → EXACTLY the fixed base (reader is the provider).
    resolved = FieldResolver(reader).resolve(tenant_id)

    # No VARIABLE fields at all — the base is purely fixed.
    assert resolved.variable_fields() == ()
    # One resolved field per FIXED_FIELDS, all FIXED, same set of dotted keys.
    assert all(f.origin is FieldOrigin.FIXED for f in resolved.fields)
    assert {f.dotted_key() for f in resolved.fields} == set(_EXPECTED_FIXED)
    assert len(resolved.fields) == len(FIXED_FIELDS)

    # Each fixed field's base attributes are preserved one-to-one.
    for rf in resolved.fields:
        expected = _EXPECTED_FIXED[rf.dotted_key()]
        actual = {
            "key": rf.key,
            "group": rf.group,
            "type": rf.type,
            "required": rf.required,
            "label": dict(rf.label),
            "choices": tuple(rf.choices) if rf.choices is not None else None,
            "order": rf.order,
            "visible": rf.visible,
        }
        assert actual == expected
