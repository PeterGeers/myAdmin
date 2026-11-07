"""
SAM property test — spec 15 (sam-page-look-and-feel), task 4.4.

**Property 8: Tenant isolation on resolve.**

Feature: sam-page-look-and-feel, Property 8: For any resolve of Look_And_Feel_Settings for a
verified tenant, the resolved values SHALL be scoped to that tenant and SHALL exclude any other
tenant's settings.

The reader under test is
:meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_look_and_feel`
(task 4.2) — the resolved-view read of Layer-1's ``look_and_feel`` slice on the SAM-owned
``config#fields`` row. Tenant scoping is enforced by the ``tenant_id``-pinned partition ``Query``
(design C4 / steering 39): the reader reads only the partition for the requested ``tenant_id``, so
one tenant's settings can never bleed into another's resolved view.

This property pins that contract observably. We generate MULTIPLE tenants, each with its OWN
distinct Look_And_Feel_Settings values, seed them all into the SAME in-memory ``FakeTable`` (whose
``query()`` returns ONLY the queried partition's items — mirroring DynamoDB's single-partition
Query, so cross-tenant items are never returned), then assert that resolving any one tenant returns
EXACTLY that tenant's stored values and never contains any value belonging only to another tenant.

The ``FakeTable`` and ``_config_fields_item`` seed helper are reused from
``test_members_projection_reader.py`` (the task-4.2 reader's own unit suite) so this property runs
on the exact same in-memory partition-isolation model the reader is tested against — no live AWS,
no MySQL (steering 34/35/39).

Hypothesis, >=100 iterations (steering 34).

Validates: Requirements 2.4
Properties: 8
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.shared.page_styles import SUPPORTED_ATTRIBUTES  # noqa: E402

# Reuse the exact in-memory DynamoDB fake + seed helper the task-4.2 reader suite uses, so this
# property runs on the same partition-isolation model (query() returns only the queried partition).
from sam.tests.test_members_projection_reader import (  # noqa: E402
    FakeTable,
    _config_fields_item,
)

# ─── Generators ────────────────────────────────────────────────────────────────────────
# A tenant id: non-empty, no reserved separators, so partition keys are distinct and valid.
_tenant_id = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=12,
).filter(lambda s: s.strip("-") != "")

# Each supported attribute draws from its permitted value space.
_hex_color = st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True)
_font_name = st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans", "Poppins"])
_base_spacing = st.sampled_from(["compact", "normal", "relaxed"])
_border_radius = st.sampled_from(["sharp", "rounded", "pill"])
_shadow_style = st.sampled_from(["none", "subtle", "medium", "dramatic"])

_ATTR_STRATEGY = {
    "color_primary": _hex_color,
    "color_accent": _hex_color,
    "font_heading": _font_name,
    "font_body": _font_name,
    "base_spacing": _base_spacing,
    "border_radius_global": _border_radius,
    "shadow_style": _shadow_style,
    # bugfix bugfix-published-form-styling (Task 8): the two new values-only attributes are
    # now supported, so tenant-isolation coverage must carry them through the slice too (their
    # stored VALUES are opaque to this resolve-scoping property; the authoritative permitted-value
    # validation lives at the edge/service plane, Task 10). (The earlier ``columns`` attribute was
    # removed — the form grid is now fully width-driven.)
    "logo": st.sampled_from(["https://assets.example.org/logo.png", "logo.svg"]),
    "header_title": st.sampled_from(["Aanmelden", "Join us"]),
}
assert set(_ATTR_STRATEGY) == set(SUPPORTED_ATTRIBUTES)


@st.composite
def _look_and_feel_values(draw):
    """Draw a NON-EMPTY look_and_feel VALUES mapping (any subset of the supported attributes).

    Non-empty so each tenant carries at least one value a sibling tenant must not see — that is
    what makes a cross-tenant leak observable.
    """
    candidate = {attr: draw(strat) for attr, strat in _ATTR_STRATEGY.items()}
    include = {attr: draw(st.booleans()) for attr in candidate}
    values = {attr: candidate[attr] for attr in candidate if include[attr]}
    # Guarantee at least one attribute so the tenant has a distinguishing value.
    if not values:
        values["color_primary"] = draw(_hex_color)
    return values


@st.composite
def _tenants_with_values(draw):
    """Draw a mapping of {tenant_id: look_and_feel_values} for >=2 distinct tenants."""
    ids = draw(
        st.lists(_tenant_id, min_size=2, max_size=6, unique=True)
    )
    return {tid: draw(_look_and_feel_values()) for tid in ids}


# ─── Property ──────────────────────────────────────────────────────────────────────────


@settings(max_examples=150)
@given(tenants=_tenants_with_values())
def test_resolve_is_scoped_to_the_tenant_and_excludes_others(tenants):
    """Property 8: a resolve returns exactly the asked tenant's values and no other tenant's.

    Feature: sam-page-look-and-feel, Property 8: For any resolve of Look_And_Feel_Settings for a
    verified tenant, the resolved values SHALL be scoped to that tenant and SHALL exclude any other
    tenant's settings.
    """
    # Seed every tenant's distinct look_and_feel slice into ONE shared table.
    table = FakeTable()
    for tenant_id, values in tenants.items():
        item = _config_fields_item(tenant_id, fields={}, overrides={})
        item["look_and_feel"] = dict(values)
        table.put(item)

    reader = MembersProjectionReader(table=table)

    for tenant_id, own_values in tenants.items():
        resolved = reader.get_look_and_feel(tenant_id)

        # 1) Scoped TO the tenant: the resolve returns exactly this tenant's stored values
        #    (the reader surfaces only supported attributes; every seeded value is supported).
        assert resolved == own_values

        # 2) Every resolved pair is this tenant's own — never sourced from a sibling.
        for attr, value in resolved.items():
            assert own_values.get(attr) == value

        # 3) Excludes OTHER tenants' settings: for any attribute this tenant did NOT store, a
        #    sibling tenant's value for that attribute must NOT appear in this resolve (that
        #    would be a cross-partition leak). An attribute this tenant DID store legitimately
        #    holds its own value, even if a sibling coincidentally stored the same value.
        for other_id, other_values in tenants.items():
            if other_id == tenant_id:
                continue
            for attr in other_values:
                if attr not in own_values:
                    assert attr not in resolved
