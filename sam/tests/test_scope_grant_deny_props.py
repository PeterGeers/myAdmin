"""
S5b Task 8.5 — property-based **scope-grant deny-by-default** tests (design Correctness
Properties).

Feature: s5b-members-runnable-in-spa, Property 4: Scope grant deny-by-default

Validates: Requirements 2.4, 2.5, 2.6, 10.6

What this asserts (the projected-grant → resolved-scope decision, via the C5 seam)
----------------------------------------------------------------------------------
Property 4 (design Correctness Properties): "For all users and dimensions, a user holding a
capability the dimension lists in ``required_for`` but having no projected ``scopegrant#`` for
that dimension resolves to an empty ``allowed_scopes`` (``access_type = "none"``) — a deny —
while an all-access grant (``*``) resolves to ``["*"]`` and a subgroup grant resolves to
exactly its granted subset."

The S5b deny-by-default AUTHORITY-preserving seam (design C5) is
``sam.members.handler.app._scope_access_from_grant(tenant_id, dimension, granted_values)``: it
maps a caller's PROJECTED grant values for one dimension onto a ``ScopeAccess`` by synthesizing
the minimal role set and delegating the classification to the domain
``resolve_scope_access`` (task 3.1), keeping the domain as the deny-by-default authority. This
suite proves Property 4 UNIVERSALLY over that seam:

Three properties, each ≥100 generated iterations (``@settings(max_examples=100)``):

- ``test_property_all_access_grant_resolves_to_wildcard`` (R2.4): for ANY valid enabled
  dimension, a projected grant of ``["*"]`` ALWAYS resolves to ``allowed_scopes == ["*"]``,
  ``access_type == "all"``, ``full_access is True``.
- ``test_property_subgroup_grant_resolves_to_exact_subset`` (R2.5): for ANY valid enabled
  dimension and ANY non-empty subset of its declared values, a projected grant of that subset
  ALWAYS resolves to EXACTLY that subset (in the dimension's declared order — the domain's
  ``_granted_values`` normalization), ``access_type == "scoped"``, never ``["*"]``.
- ``test_property_absent_grant_on_required_dimension_denies`` (R2.6, the critical one): for
  ANY valid enabled dimension with a non-empty ``required_for``, an ABSENT projected grant
  (``None``) ALWAYS resolves to ``allowed_scopes == []``, ``access_type == "none"`` (deny).
  This is asserted as UNIVERSAL — an absent grant NEVER falls through to ``["*"]`` or any
  non-empty set. Deny-by-default is the default, not a special case.

Plus a couple of Layer-B end-to-end example checks that drive the SAME outcomes through the
projection reader (``MembersProjectionReader.get_scope_grants``) + the edge seam over an
in-memory ``FakeTable``, seeding a ``config#scope`` (a ``required_for`` dimension) row and,
for the granted cases, a ``scopegrant#<email>#<dimension>`` row.

No live AWS, no MySQL: the reader queries an in-memory ``FakeTable`` (mirrors
``sam/tests/test_config_roundtrip_props.py`` / ``sam/tests/test_empty_is_valid_props.py``).
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

# The S5b deny-by-default authority-preserving seam (design C5) — module-level in app.py.
from sam.members.handler.app import _scope_access_from_grant
from sam.members.domain.scope_dimensions import WILDCARD, ScopeDimension
from sam.members.repository.projection_config_reader import MembersProjectionReader


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (query side only) — mirrors the example tests
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory query-side stand-in for a boto3 DynamoDB Table.

    ``query(KeyConditionExpression=...)`` returns ONLY the seeded items whose partition key
    matches the boto3 ``Key(...).eq(...)`` condition (mirrors the existing property tests).
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
# Strategies — generate a VALID, enabled ScopeDimension with a non-empty required_for
# ---------------------------------------------------------------------------

# A non-blank identifier token (keys / values / role names). Free of the wildcard sentinel by
# construction (alphabet excludes ``*``).
_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)


@st.composite
def _valid_dimension(draw, *, require_all_wildcard=False):
    """A VALID, enabled :class:`ScopeDimension` with a non-empty ``required_for``.

    Enforces the invariants ``ScopeDimension`` / ``ScopeConfig`` validation requires so the
    domain never raises for the wrong reason:

    - non-blank ``key``;
    - ≥1 unique non-blank ``values`` (an enabled dimension must declare at least one value);
    - an ``all_wildcard`` role that is NEVER one of the values (it is a role name);
    - a non-empty ``required_for`` (so the deny is a genuine ``required_for`` deny — R2.6).

    ``require_all_wildcard`` forces a declared ``all_wildcard`` role. This models the input
    space where a projected all-access grant (``["*"]``) is actually authored: per design C4,
    the projection sync only emits ``["*"]`` for a user holding the dimension's all-access
    ROLE, which exists only when the dimension declares an ``all_wildcard`` (h-dcn's
    ``Regio_All``). The deny (4c) and subset (4b) properties do NOT need it and stay universal
    over ALL valid dimensions (with or without an ``all_wildcard``).
    """
    key = draw(_TOKEN)
    values = draw(st.lists(_TOKEN, min_size=1, max_size=5, unique=True))
    # all_wildcard is a role name; must not collide with a scope value.
    wildcard_strategy = _TOKEN.filter(lambda w: w not in set(values))
    if not require_all_wildcard:
        wildcard_strategy = st.one_of(st.none(), wildcard_strategy)
    all_wildcard = draw(wildcard_strategy)
    required_for = draw(st.lists(_TOKEN, min_size=1, max_size=3, unique=True))
    return ScopeDimension(
        key=key,
        enabled=True,
        multi_valued=draw(st.booleans()),
        values=tuple(values),
        all_wildcard=all_wildcard,
        required_for=tuple(required_for),
    )


_TENANT = "deny-props-tenant"


# ---------------------------------------------------------------------------
# Property 4a — an all-access ("*") projected grant ALWAYS resolves to ["*"] (R2.4)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(dim=_valid_dimension(require_all_wildcard=True))
def test_property_all_access_grant_resolves_to_wildcard(dim):
    """Feature: s5b-members-runnable-in-spa, Property 4: Scope grant deny-by-default.

    Validates: Requirements 2.4, 2.5, 2.6, 10.6

    For ANY valid enabled dimension that declares an ``all_wildcard`` role (the input space in
    which a projected all-access grant is authored — see the generator note), a projected
    all-access grant (``["*"]``) ALWAYS resolves to tenant-wide ``["*"]`` (``access_type="all"``,
    ``full_access``).
    """
    access = _scope_access_from_grant(_TENANT, dim, [WILDCARD])
    assert access.allowed_scopes == [WILDCARD]
    assert access.allowed_scopes == ["*"]
    assert access.full_access is True
    assert access.access_type == "all"


# ---------------------------------------------------------------------------
# Property 4b — a subgroup grant ALWAYS resolves to exactly its subset (R2.5)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data(), dim=_valid_dimension())
def test_property_subgroup_grant_resolves_to_exact_subset(data, dim):
    """Feature: s5b-members-runnable-in-spa, Property 4: Scope grant deny-by-default.

    Validates: Requirements 2.4, 2.5, 2.6, 10.6

    For ANY valid enabled dimension and ANY non-empty subset of its declared values, a
    projected subgroup grant of that subset ALWAYS resolves to EXACTLY that subset — in the
    dimension's declared order (the domain's ``_granted_values`` de-dup/order normalization) —
    with ``access_type="scoped"`` and never a wildcard.
    """
    declared = list(dim.values)
    # A non-empty subset of the declared values (the projected scopegrant# values).
    subset = data.draw(
        st.lists(st.sampled_from(declared), min_size=1, max_size=len(declared), unique=True)
    )
    access = _scope_access_from_grant(_TENANT, dim, subset)

    # Exactly the granted subset, normalized to the dimension's declared order.
    expected = [v for v in declared if v in set(subset)]
    assert access.allowed_scopes == expected
    assert set(access.allowed_scopes) == set(subset)
    assert access.access_type == "scoped"
    assert access.full_access is False
    assert WILDCARD not in access.allowed_scopes


# ---------------------------------------------------------------------------
# Property 4c — an ABSENT grant on a required_for dimension ALWAYS denies (R2.6) — CRITICAL
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(dim=_valid_dimension())
def test_property_absent_grant_on_required_dimension_denies(dim):
    """Feature: s5b-members-runnable-in-spa, Property 4: Scope grant deny-by-default.

    Validates: Requirements 2.4, 2.5, 2.6, 10.6

    THE critical universal property (R2.6, deny-by-default): for ANY valid enabled dimension
    with a non-empty ``required_for``, an ABSENT projected grant (``None``) ALWAYS resolves to
    a hard deny — ``allowed_scopes == []``, ``access_type == "none"``, ``is_denied()``. This
    NEVER falls through to ``["*"]`` or any non-empty set. Deny is the default, not a case.
    """
    assert dim.required_for  # guard: the deny is a genuine required_for deny
    access = _scope_access_from_grant(_TENANT, dim, None)

    assert access.allowed_scopes == []
    assert access.access_type == "none"
    assert access.full_access is False
    assert access.is_denied() is True
    # Universality: an absent grant is NEVER tenant-wide and NEVER a non-empty grant.
    assert access.allowed_scopes != [WILDCARD]
    assert len(access.allowed_scopes) == 0


# ---------------------------------------------------------------------------
# Layer-B end-to-end example checks — the reader + edge seam over a FakeTable
# ---------------------------------------------------------------------------

# A concrete required_for dimension for the end-to-end examples (mirrors h-dcn's region).
_E2E_DIMENSION = ScopeDimension(
    key="region",
    enabled=True,
    values=("Noord", "Zuid", "Oost", "West"),
    all_wildcard="Regio_All",
    required_for=("Members_CRUD",),
)
_E2E_EMAIL = "user@example.com"


def _config_scope_item(tenant_id, dim):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
        "dimensions": [
            {
                "key": dim.key,
                "enabled": dim.enabled,
                "multi_valued": dim.multi_valued,
                "values": list(dim.values),
                "all_wildcard": dim.all_wildcard,
                "required_for": list(dim.required_for),
            }
        ],
        schema.VERSION_ATTR: 1,
    }


def _scopegrant_item(tenant_id, email, dimension, values):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_SCOPEGRANT, email, dimension
        ),
        "dimension": dimension,
        "values": list(values),
        schema.VERSION_ATTR: 1,
    }


def _seed(rows):
    table = FakeTable()
    for row in rows:
        table.put(row)
    return table


def test_e2e_absent_scopegrant_row_denies():
    """R2.6 end-to-end: a config#scope required_for dimension with NO scopegrant# row for the
    caller → the reader yields no grant for that dimension → the edge seam denies (``[]``)."""
    table = _seed([_config_scope_item(_TENANT, _E2E_DIMENSION)])
    reader = MembersProjectionReader(table=table)

    grants = reader.get_scope_grants(_TENANT, _E2E_EMAIL)
    granted = grants.get(_E2E_DIMENSION.key)  # ABSENT → None
    granted_list = list(granted) if granted is not None else None

    access = _scope_access_from_grant(_TENANT, _E2E_DIMENSION, granted_list)
    assert access.allowed_scopes == []
    assert access.access_type == "none"


def test_e2e_all_access_scopegrant_row_resolves_to_wildcard():
    """R2.4 end-to-end: a projected ``scopegrant#`` row of ``["*"]`` → tenant-wide ``["*"]``."""
    table = _seed(
        [
            _config_scope_item(_TENANT, _E2E_DIMENSION),
            _scopegrant_item(_TENANT, _E2E_EMAIL, _E2E_DIMENSION.key, [WILDCARD]),
        ]
    )
    reader = MembersProjectionReader(table=table)

    grants = reader.get_scope_grants(_TENANT, _E2E_EMAIL)
    granted_list = list(grants[_E2E_DIMENSION.key])

    access = _scope_access_from_grant(_TENANT, _E2E_DIMENSION, granted_list)
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


def test_e2e_subgroup_scopegrant_row_resolves_to_subset():
    """R2.5 end-to-end: a projected ``scopegrant#`` row of a subset → exactly that subset."""
    table = _seed(
        [
            _config_scope_item(_TENANT, _E2E_DIMENSION),
            _scopegrant_item(_TENANT, _E2E_EMAIL, _E2E_DIMENSION.key, ["Noord", "West"]),
        ]
    )
    reader = MembersProjectionReader(table=table)

    grants = reader.get_scope_grants(_TENANT, _E2E_EMAIL)
    granted_list = list(grants[_E2E_DIMENSION.key])

    access = _scope_access_from_grant(_TENANT, _E2E_DIMENSION, granted_list)
    # Declared order: Noord before West.
    assert access.allowed_scopes == ["Noord", "West"]
    assert access.access_type == "scoped"
