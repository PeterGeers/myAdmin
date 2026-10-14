"""
Phase 3 (Members config redesign — reshape-model-and-ui) Task 2.3 — **Property 2**:
scope resolution is equivalent across the authoring-representation change.

Feature: phase-3-reshape-model-and-ui, Property 2.

Validates: Requirements 2.3, 2.5, 2.6

What this asserts (the whole safety story of step 9)
----------------------------------------------------
Phase 3 step 9 moves the AUTHORING representation of a tenant's scope-binding from a
standalone ``members.scope_dimensions`` list onto the field itself: a field declares, via a
``scope`` attribute on the ``members.field_overlay`` object, that it is a scope axis — enabled,
with its value vocabulary (and optional label / ``required_for``). The resolution code in
``sam/members/handler/app.py`` (``resolve_scope_access_for_config`` → ``allowed_scopes``) and
the ``scopegrant#`` grants model are LEFT UNCHANGED (R2.3/R2.4).

The behaviour-preservation contract (R2.5/R2.6, design Property 2) is that for ANY tenant scope
config and ANY user scope grants, the ``allowed_scopes`` the resolver computes AFTER scope is
authored as a field attribute equals the ``allowed_scopes`` it computed BEFORE — the authoring
representation changes, the resolved access does not.

Where the equivalence lives (and why it is asserted here)
---------------------------------------------------------
The equivalence is enforced at the PROJECTION boundary: both authoring shapes converge on the
SAME ``config#scope`` row (the Flask builder's ``_scope_dimensions_from_overlay`` derives a
dimension from a field's ``scope`` attribute via the exact same ``_map_scope_dimension`` the
standalone ``scope_dimensions`` list uses, keyed by the field's own key). That row is rebuilt
1:1 by the UNCHANGED ``MembersProjectionReader`` into a ``ScopeConfig``, which the UNCHANGED
resolver consumes. So the honest place to pin Property 2 is end-to-end through the real builder,
the real reader, and the real resolver — asserting the resolved ``allowed_scopes`` are identical
for the two authoring representations of the SAME config, over arbitrary user grants.

This mirrors ``sam/tests/test_config_roundtrip_props.py`` (which already reaches the Flask-plane
``services.projection_sync`` builders + the ``MembersProjectionReader`` from the SAM suite via
``FakeParameterService`` / ``FakeTable``). No live AWS, no MySQL — the builder reads a fake
parameter service and the reader queries a fake table; the resolver is pure.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so the Flask-plane `services.*` builders resolve (mirrors
# test_config_roundtrip_props.py reaching `services.projection_sync` from the SAM suite).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services.projection_sync import build_config_scope_row

from sam.members.domain.scope_access import (
    ADMIN_ROLE_DEFAULTS,
    resolve_scope_access_for_config,
)
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.tests.test_config_roundtrip_props import FakeParameterService, FakeTable

_TENANT_ID = "scope-equiv-tenant"


# ---------------------------------------------------------------------------
# Strategies — an arbitrary tenant scope config, plus arbitrary user grants.
#
# A field-authorable scope axis binds the dimension to the FIELD'S OWN KEY (both the
# dimension `key` and bound `field` derive from the field key — `_scope_dimension_from_field`),
# exactly as every current standalone dimension already binds (`ScopeDimension.field` defaults
# to its `key`). So the equivalence is between a standalone dimension whose `key == field` and
# the same axis authored on that field; the generators enforce `key == field` so the two
# representations describe the SAME config (not two different ones).
# ---------------------------------------------------------------------------

_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)


def _i18n_label():
    return st.dictionaries(
        keys=st.sampled_from(["nl", "en", "de", "fr"]),
        values=st.text(min_size=1, max_size=20),
        max_size=4,
    )


@st.composite
def _scope_axis(draw, key: str):
    """One VALID authored scope axis for ``key`` — the facts common to BOTH representations.

    An enabled axis declares >=1 unique non-blank value (the ``ScopeConfig`` validation rule the
    reader re-applies); a disabled axis is a no-op (tenant-wide collapse) but still carries a
    well-formed value set for simplicity. ``required_for`` is a list of capability names.
    """
    return {
        "key": key,
        "enabled": draw(st.booleans()),
        "values": draw(st.lists(_TOKEN, min_size=1, max_size=5, unique=True)),
        "label": draw(_i18n_label()),
        "required_for": draw(st.lists(_TOKEN, max_size=3, unique=True)),
    }


@st.composite
def _scope_config(draw):
    """A tenant scope config: 1..4 axes with UNIQUE keys (each binds to its own field key)."""
    keys = draw(st.lists(_TOKEN, min_size=1, max_size=4, unique=True))
    return [draw(_scope_axis(key)) for key in keys]


def _standalone_dimensions(axes: list[dict]) -> list[dict]:
    """Authoring representation BEFORE: the standalone ``members.scope_dimensions`` list.

    Each axis is a dimension dict keyed by (and bound to) the field key — the shape the
    standalone ``scope_dimensions`` param has always carried.
    """
    return [
        {
            "key": a["key"],
            "field": a["key"],
            "enabled": a["enabled"],
            "values": list(a["values"]),
            "label": dict(a["label"]),
            "required_for": list(a["required_for"]),
        }
        for a in axes
    ]


def _field_overlay_with_scope(axes: list[dict]) -> dict:
    """Authoring representation AFTER: scope-as-a-field-attribute on ``members.field_overlay``.

    Each axis becomes a field in the overlay carrying a ``scope`` sub-object
    ``{enabled, values, label?, required_for?}`` — the field-attribute shape the Flask builder's
    ``_scope_dimensions_from_overlay`` derives the ``config#scope`` dimensions from. The field
    key IS the axis key, so the derived dimension binds the axis to its own field (identical to
    the standalone representation above).
    """
    fields = {
        a["key"]: {
            "key": a["key"],
            "type": "enum",
            "choices": list(a["values"]),
            "scope": {
                "enabled": a["enabled"],
                "values": list(a["values"]),
                "label": dict(a["label"]),
                "required_for": list(a["required_for"]),
            },
        }
        for a in axes
    }
    return {"fields": fields, "fixed_overrides": {}}


def _resolve_config(scope_dimensions=None, field_overlay=None) -> ScopeConfig:
    """Author one representation -> builder -> fake table -> reader -> resolved ``ScopeConfig``.

    Drives the config through the REAL projection path: ``build_config_scope_row`` (which prefers
    scope-as-field-attribute and falls back to the standalone list), then the UNCHANGED
    ``MembersProjectionReader`` rebuild. Returns the resolved ``ScopeConfig`` the resolver reads.
    """
    stored: dict = {}
    if scope_dimensions is not None:
        stored[("members", "scope_dimensions", _TENANT_ID)] = scope_dimensions
    if field_overlay is not None:
        stored[("members", "field_overlay", _TENANT_ID)] = field_overlay

    params = FakeParameterService(stored)
    row = build_config_scope_row({"administration": _TENANT_ID}, params)
    assert row is not None

    table = FakeTable()
    table.put(row.to_dynamodb_item())
    return MembersProjectionReader(table=table).get_scope_config(_TENANT_ID)


@st.composite
def _user_grants(draw, axes: list[dict]):
    """Arbitrary user scope grants (the ``user_roles`` the resolver resolves against).

    A realistic mix the resolver must handle identically under either representation:
    bare declared-value names (scoped grants) drawn from the axes' own vocabularies, admin
    role names, ``required_for`` capability names (held without a grant -> deny), and arbitrary
    noise. Deny-by-default and admin-wildcard are therefore both exercised.
    """
    vocab = sorted({v for a in axes for v in a["values"]})
    caps = sorted({c for a in axes for c in a["required_for"]})
    pool = st.one_of(
        st.sampled_from(vocab) if vocab else st.nothing(),
        st.sampled_from(sorted(ADMIN_ROLE_DEFAULTS)),
        st.sampled_from(caps) if caps else st.nothing(),
        _TOKEN,
    )
    return draw(st.lists(pool, max_size=6, unique=True))


# ---------------------------------------------------------------------------
# Property 2 — scope resolution is equivalent across the authoring-representation change.
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(data=st.data())
def test_property_scope_resolution_equivalent_across_authoring_change(data):
    """Feature: phase-3-reshape-model-and-ui, Property 2.

    Validates: Requirements 2.3, 2.5, 2.6

    For ANY tenant scope config expressed BOTH ways (standalone ``members.scope_dimensions`` vs
    scope-as-a-field-attribute on ``members.field_overlay``) and ANY user scope grants, the
    ``allowed_scopes`` (and ``access_type``) the UNCHANGED resolver computes are IDENTICAL — the
    authoring representation changes, the resolved access does not.
    """
    axes = data.draw(_scope_config())

    before = _resolve_config(scope_dimensions=_standalone_dimensions(axes))
    after = _resolve_config(field_overlay=_field_overlay_with_scope(axes))

    # The resolved ``ScopeConfig`` is the same tenant-wide-ness either way (sanity: the two
    # representations describe the same config, so the collapse decision matches).
    assert before.is_tenant_wide() == after.is_tenant_wide()

    # Resolve EACH axis under the SAME arbitrary user grants and assert identical access.
    for axis in axes:
        grants = data.draw(_user_grants(axes))
        access_before = resolve_scope_access_for_config(before, axis["key"], grants)
        access_after = resolve_scope_access_for_config(after, axis["key"], grants)

        assert access_after.allowed_scopes == access_before.allowed_scopes
        assert access_after.access_type == access_before.access_type
        assert access_after.full_access == access_before.full_access


@settings(max_examples=200)
@given(data=st.data())
def test_property_scope_config_rows_match_across_authoring_change(data):
    """Feature: phase-3-reshape-model-and-ui, Property 2 (projection-boundary leg).

    Validates: Requirements 2.3, 2.5

    The equivalence is enforced at the projection boundary: the ``ScopeConfig`` the reader
    rebuilds from the field-attribute authoring is dimension-for-dimension equal to the one it
    rebuilds from the standalone ``scope_dimensions`` list (same keys, fields, enabled flags,
    values, labels, required_for). This is the structural reason the resolver — unchanged —
    cannot tell the two representations apart.
    """
    axes = data.draw(_scope_config())

    before = _resolve_config(scope_dimensions=_standalone_dimensions(axes))
    after = _resolve_config(field_overlay=_field_overlay_with_scope(axes))

    def _comparable(cfg: ScopeConfig):
        return [
            {
                "key": d.key,
                "field": d.field,
                "enabled": d.enabled,
                "values": tuple(d.values),
                "label": dict(d.label),
                "required_for": tuple(d.required_for),
            }
            for d in cfg.dimensions
        ]

    assert _comparable(after) == _comparable(before)
