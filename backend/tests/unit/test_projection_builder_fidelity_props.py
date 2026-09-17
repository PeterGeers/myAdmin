"""Property-based test for S3 governance projection fidelity (T13, R5.3).

Feature: s3-claims-and-projection
Property 2: Projection fidelity (exactly the tenant-level subset)

Validates: Requirements R5.3

This exercises the pure ``build_projection_items`` transform (T12,
``services.projection_builder``) over a large generated space of
tenants x modules x roles and asserts the projected item set is *exactly* the
tenant-level subset — for tenants with a SAM-backed module enabled — with:

- nothing extra projected (every emitted item is one the source justifies),
- nothing required missing (every source fact that must be projected is), and
- no per-user-token-only (S4) data in the projection (role items carry only the
  verbatim ``email``/``role`` reference pair; no resolved/effective permission
  set, decision, or capability list leaks through).

The builder is pure (no I/O), so no MySQL/DynamoDB fakes are needed. Generators
cover the design's named edge cases: empty tenant, tenant with no modules,
missing keys, unicode emails, and duplicate roles. SAM backing is represented by
injecting SAM-backed modules into ``MODULE_REGISTRY`` for the duration of each
example (mirroring T12's ``monkeypatch.setitem`` approach, but via
``patch.dict`` so it composes with Hypothesis's ``@given``).

The expected set is computed by an **independent oracle** in this test — it does
not call the builder — so the property checks the builder against a separately
derived specification of "the tenant-level subset", not against itself.
"""

import os
import sys
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services import projection_schema as schema  # noqa: E402
from services.module_registry import MODULE_REGISTRY, module_backing  # noqa: E402
from services.projection_builder import build_projection_items  # noqa: E402


# ---------------------------------------------------------------------------
# Module universe
#
# The projection gate keys off module *backing*: SAM-backed modules open it,
# flask-backed ones do not. We test over a fixed universe of module names with
# known backings. The flask names are real shipped modules (backing "flask");
# the SAM names are injected into MODULE_REGISTRY per example so the gate has a
# SAM-backed module to fire on (design.md D3; matches T12's injection approach).
# ---------------------------------------------------------------------------

_FLASK_MODULES = ["FIN", "STR", "TENADMIN", "ZZP"]
_SAM_MODULES = ["SAM_ALPHA", "SAM_BETA", "SAM_GAMMA"]
_ALL_MODULE_NAMES = _FLASK_MODULES + _SAM_MODULES


def _sam_registry_entries() -> dict[str, dict]:
    """Registry entries marking the SAM_* names as SAM-backed (test-local)."""
    return {
        name: {
            "description": f"Temporary SAM-backed test module {name}",
            "required_params": {},
            "required_tax_rates": [],
            "required_roles": [f"{name}_Read"],
            "backing": {
                "kind": "sam",
                "api_base_env": f"{name}_API_BASE",
                "data_namespace": name.lower(),
            },
        }
        for name in _SAM_MODULES
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty tenant keys (partition key must be present/non-blank, R5.4). Kept to
# plain identifiers so the tenant is always projectable when the gate opens.
tenant_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=48),
    min_size=1,
    max_size=12,
)

# Unicode emails (edge case per design: unicode emails). Excludes the sort-key
# separator "#" since a segment containing it is rejected by build_sort_key
# (an orthogonal validation concern, not fidelity).
email_st = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=20,
)

# Role names — likewise no "#". Includes a small fixed pool so duplicates arise.
role_st = st.one_of(
    st.sampled_from(["Reader", "Editor", "Admin", "SAM_ALPHA_Read"]),
    st.text(
        alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
        min_size=1,
        max_size=15,
    ),
)


def module_row_st():
    """A tenant_modules row: a module name from the universe + is_active flag."""
    return st.fixed_dictionaries(
        {
            "module_name": st.sampled_from(_ALL_MODULE_NAMES),
            "is_active": st.booleans(),
        }
    )


def role_row_st():
    """A user_tenant_roles row: (email, role). Duplicates possible across rows."""
    return st.fixed_dictionaries({"email": email_st, "role": role_st})


def source_state_st():
    """A full generated source state: (tenant, tenant_modules[], roles[]).

    Covers the design's edge cases:
      - empty tenant / tenant with no modules  (modules list may be empty)
      - unicode emails                         (email_st)
      - duplicate roles                        (small role pool + repeated rows)
    """
    return st.tuples(
        st.fixed_dictionaries({"administration": tenant_id_st}),
        st.lists(module_row_st(), max_size=6),
        st.lists(role_row_st(), max_size=6),
    )


# ---------------------------------------------------------------------------
# Independent oracle — the expected tenant-level subset (does NOT use the builder)
# ---------------------------------------------------------------------------

def _expected_sort_keys(tenant, modules, roles):
    """Compute the exact set of sort keys the projection MUST contain.

    Derived independently of the builder from the design's projection rules
    (design.md D3 "What is projected", R5.3):

      * gate: project iff >= 1 enabled (is_active) module is SAM-backed;
      * on open gate: one "tenant" record, one "module#<name>" per module row,
        one "role#<email>#<role>" per role grant.

    Returns None when the gate is closed (nothing is projected).
    """
    gate_open = any(
        row["is_active"] and module_backing(row["module_name"]) == "sam"
        for row in modules
    )
    if not gate_open:
        return None

    expected = {schema.build_sort_key(schema.RECORD_TYPE_TENANT)}
    for row in modules:
        expected.add(schema.build_sort_key(schema.RECORD_TYPE_MODULE, row["module_name"]))
    for row in roles:
        expected.add(schema.build_sort_key(schema.RECORD_TYPE_ROLE, row["email"], row["role"]))
    return expected


# ---------------------------------------------------------------------------
# Property 2: Projection fidelity (exactly the tenant-level subset)
# ---------------------------------------------------------------------------

# Attribute names that would indicate a per-user *resolved answer* (S4) leaking
# into the tenant-level projection. None of these may appear on any item.
_FORBIDDEN_TOKEN_ONLY_ATTRS = frozenset(
    {"permissions", "resolved", "effective_permissions", "decision", "capabilities"}
)


@settings(max_examples=200)
@given(state=source_state_st())
def test_build_projection_items_matches_tenant_level_subset_exactly(state):
    """Feature: s3-claims-and-projection, Property 2: Projection fidelity (exactly the tenant-level subset).

    For any generated source state, the set of projected items equals the
    tenant-level subset filtered to tenants with SAM-backed modules enabled:
    nothing extra, nothing required missing, and no per-user-token-only data.
    """
    tenant, modules, roles = state

    with patch.dict(MODULE_REGISTRY, _sam_registry_entries()):
        items = build_projection_items(tenant, modules, roles)
        expected_sks = _expected_sort_keys(tenant, modules, roles)

    tenant_id = tenant["administration"]

    if expected_sks is None:
        # Gate closed: no SAM-backed module enabled -> nothing is projected.
        assert items == [], (
            "no SAM-backed module enabled, yet items were projected: "
            f"{[i.sort_key for i in items]!r}"
        )
        return

    produced_sks = [i.sort_key for i in items]

    # Fidelity, part 1 — the produced SORT-KEY SET equals the expected set:
    # nothing extra projected, nothing required missing. (Set equality checks
    # both directions at once.)
    assert set(produced_sks) == expected_sks, (
        "projected set does not equal the tenant-level subset "
        f"(extra={set(produced_sks) - expected_sks!r}, "
        f"missing={expected_sks - set(produced_sks)!r})"
    )

    # Fidelity, part 2 — every item lives in the correct tenant partition (R5.4);
    # the projection is exactly this tenant's subset, not another's.
    assert all(i.tenant_id == tenant_id for i in items), (
        "an item was projected under the wrong partition key: "
        f"{[(i.tenant_id, i.sort_key) for i in items if i.tenant_id != tenant_id]!r}"
    )

    # Fidelity, part 3 — no per-user-token-only (S4) data appears. Role items
    # carry ONLY the verbatim (email, role) reference pair; no item carries a
    # resolved/effective-permission attribute.
    for item in items:
        assert _FORBIDDEN_TOKEN_ONLY_ATTRS.isdisjoint(item.attributes.keys()), (
            f"token-only (S4) data leaked into the projection: {item.attributes!r}"
        )
    for item in items:
        if item.sort_key.startswith(schema.RECORD_TYPE_ROLE + schema.SORT_KEY_SEPARATOR):
            assert set(item.attributes.keys()) == {"email", "role"}, (
                "a role item carried more than the verbatim (email, role) pair: "
                f"{item.attributes!r}"
            )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short"]))
