"""
SAM property test — spec 15 (sam-page-look-and-feel), task 5.4.

**Property 9: Copy is a one-time independent snapshot.**

Feature: sam-page-look-and-feel, Property 9: For any source and target Page of the same tenant,
after a Layer-1 copy the target's values SHALL equal the source's at copy time, and any subsequent
change to either Page's values SHALL NOT alter the other's.

The operation under test is
:meth:`sam.members.domain.look_and_feel_settings_service.LookAndFeelSettingsService.copy_settings`
(task 5.3) — the Layer-1 one-time snapshot copy of a Page's look-and-feel VALUES onto another Page
of the SAME verified tenant (Req 9). It reads the source Page's resolved view and issues a SINGLE
``copy_look_and_feel`` snapshot op on the target; it establishes NO live link between source and
target, so a later change to either Page leaves the other untouched by construction.

Modelling the independence (why these fakes)
--------------------------------------------
The service's reader/writer seams are tenant-scoped (``page_id`` resolves today to the one
SAM-owned page — the application form's ``look_and_feel`` slice on ``config#fields``), and the copy
runs within ONE verified tenant (Req 9.4 forbids a cross-tenant source). To model a SOURCE and a
TARGET Page as *independent stored slices* that the service reads/writes — so we can mutate one and
assert the other is unaffected — we back the reader and writer by two distinct per-tenant stores
and run the service once per side:

- a SOURCE service (reader+writer over the source store) is used to author the source values and to
  perform the copy READ (``get_settings`` / the copy's source read resolve the source store);
- a TARGET service (reader+writer over the target store) receives the snapshot and is used to author
  later target mutations.

The writer's ``copy_look_and_feel`` applies the snapshot into the TARGET store as a fresh
``dict(...)`` (the one-time value snapshot — no shared reference), exactly as the real Change-Op
``SET look_and_feel = :snapshot`` overwrites the stored slice. ``set``/``remove`` ops mutate only
their own store. Nothing is wired between the two stores, so independence holds by construction —
which is precisely what this property pins observably.

Hypothesis, >=100 iterations (steering 34). Test-only — product code is untouched.

Validates: Requirements 9.1, 9.2, 9.3, 9.5
Properties: 9
"""

from __future__ import annotations

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

from sam.members.domain.look_and_feel_settings_service import (  # noqa: E402
    APPLICATION_FORM_PAGE_ID,
    LookAndFeelSettingsService,
    _COLOUR_ATTRIBUTES,
    _COLUMNS_ATTRIBUTE,
    _FONT_ATTRIBUTES,
    _HEADER_TITLE_ATTRIBUTE,
    _LOGO_ATTRIBUTE,
    _MAX_COLUMNS,
    _MAX_HEADER_TITLE_LENGTH,
    _MIN_COLUMNS,
    _PERMITTED_VALUES,
)
from sam.shared.page_styles import SUPPORTED_ATTRIBUTES  # noqa: E402

# The attributes the SERVICE validates (enum + colour + font + the bugfix extension columns / logo
# / header_title). The bugfix ``bugfix-published-form-styling`` Task 10 added the permitted-value
# rules for the new three, so the service-driven value pool below covers EXACTLY the full generator
# set of ten.
_SERVICE_VALIDATED_ATTRS = (
    set(_PERMITTED_VALUES)
    | set(_COLOUR_ATTRIBUTES)
    | set(_FONT_ATTRIBUTES)
    | {_COLUMNS_ATTRIBUTE, _LOGO_ATTRIBUTE, _HEADER_TITLE_ATTRIBUTE}
)

_TENANT = "h-dcn"


# ── In-memory store + reader/writer seams (no boto3, no DynamoDB) ────────────────────────


class _Store:
    """A single tenant's stored ``look_and_feel`` VALUES slice — an in-memory stand-in for the
    ``config#fields`` slice the real reader resolves and the real Change-Op writer mutates.

    Models ONE Page's slice. A source Page and a target Page are two SEPARATE ``_Store`` instances
    so a mutation to one cannot reach the other except through the service's own ops — which is how
    we observe that the copy establishes no live link (Req 9.2 / 9.5).
    """

    def __init__(self, values: dict | None = None):
        # Store a fresh copy so the seed mapping the test holds is never aliased by the store.
        self._values: dict = dict(values or {})

    # Reader seam: a tenant-scoped resolved-view read (a fresh dict — never a live reference).
    def get_look_and_feel(self, tenant_id: str):
        return dict(self._values)

    # Writer seams: each applies a single scoped Change-Op to THIS store only.
    def set_look_and_feel(self, tenant_id, attribute, value, *, client_op_id=None):
        self._values[attribute] = value
        return {"version": "v-next", "idempotent_replay": False}

    def remove_look_and_feel(self, tenant_id, attribute, *, client_op_id=None):
        self._values.pop(attribute, None)
        return {"version": "v-next", "idempotent_replay": False}

    def copy_look_and_feel(self, tenant_id, snapshot_values, *, client_op_id=None):
        # SET look_and_feel = :snapshot — overwrite with a FRESH dict (one-time value snapshot,
        # no shared reference back to the source store).
        self._values = dict(snapshot_values)
        return {"version": "v-next", "idempotent_replay": False}

    def snapshot(self) -> dict:
        """What ``get_settings`` would resolve for this Page right now (a plain copy)."""
        return dict(self._values)


def _service_over(store: _Store) -> LookAndFeelSettingsService:
    # The same store is both the reader and the writer seam for one Page (reads and writes resolve
    # to the one SAM-owned slice — as in production, where page_id -> the application form slice).
    return LookAndFeelSettingsService(store, store)


def _copy_service(source_store: _Store, target_store: _Store) -> LookAndFeelSettingsService:
    """A service whose READ seam is the source Page's store and whose WRITE seam is the target
    Page's store — so a real ``copy_settings`` call reads the source's resolved view and applies the
    one-time snapshot onto the (independent) target store. This drives the ACTUAL product method
    (not a hand-inlined copy) while still modelling source and target as two independent slices.
    """
    return LookAndFeelSettingsService(source_store, target_store)


# ── Value generators (each attribute's PERMITTED set, so set_setting accepts them) ───────

_VALID_BY_ATTR = {
    "color_primary": st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True),
    "color_accent": st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True),
    "font_heading": st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans"]),
    "font_body": st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans"]),
    "base_spacing": st.sampled_from(sorted(_PERMITTED_VALUES["base_spacing"])),
    "border_radius_global": st.sampled_from(sorted(_PERMITTED_VALUES["border_radius_global"])),
    "shadow_style": st.sampled_from(sorted(_PERMITTED_VALUES["shadow_style"])),
    # bugfix ``bugfix-published-form-styling`` Task 10 — the three new values-only attributes, each
    # drawn from its PERMITTED set so ``set_setting`` accepts them.
    "columns": st.integers(min_value=_MIN_COLUMNS, max_value=_MAX_COLUMNS),
    "logo": st.sampled_from(
        [
            "https://assets.example.org/logo.png",
            "https://cdn.example.net/brand/mark.svg",
            "/assets/logo.png",
        ]
    ),
    "header_title": st.text(min_size=1, max_size=_MAX_HEADER_TITLE_LENGTH).filter(
        lambda s: bool(s.strip())
    ),
}
# These values are driven through ``set_setting``, so the pool must cover EXACTLY the attributes the
# SERVICE validates. The bugfix ``bugfix-published-form-styling`` Task 10 (edge + service plane)
# added the permitted-value rules for the new three (columns / logo / header_title), so this
# copy-snapshot property now exercises the FULL generator set of ten.
assert set(_VALID_BY_ATTR) == _SERVICE_VALIDATED_ATTRS
assert _SERVICE_VALIDATED_ATTRS == set(SUPPORTED_ATTRIBUTES)


@st.composite
def _values_slice(draw):
    """Draw an arbitrary (possibly empty) slice of VALID look-and-feel values."""
    values = {}
    for attr, strat in _VALID_BY_ATTR.items():
        if draw(st.booleans()):
            values[attr] = draw(strat)
    return values


@st.composite
def _single_valid(draw):
    """Draw one (attribute, valid value) pair for a subsequent mutation.

    The mutation is applied via the SERVICE (``set_setting``), so the attribute is drawn from the
    service-validated set — a subset of the generator's SUPPORTED_ATTRIBUTES until Task 10 adds the
    new three's permitted-value rules.
    """
    attr = draw(st.sampled_from(sorted(_SERVICE_VALIDATED_ATTRS)))
    return attr, draw(_VALID_BY_ATTR[attr])


# ── Property ─────────────────────────────────────────────────────────────────────────────


# Tag (exact, single-line):
# Feature: sam-page-look-and-feel, Property 9: For any source and target Page of the same tenant, after a Layer-1 copy the target's values SHALL equal the source's at copy time, and any subsequent change to either Page's values SHALL NOT alter the other's.
@settings(max_examples=200)
@given(
    source_values=_values_slice(),
    target_values=_values_slice(),
    source_mutation=_single_valid(),
    target_mutation=_single_valid(),
)
def test_copy_is_a_one_time_independent_snapshot(
    source_values, target_values, source_mutation, target_mutation
):
    """Property 9: after a copy the target equals the source at copy time, and later changes to
    either Page do not alter the other.

    Feature: sam-page-look-and-feel, Property 9: For any source and target Page of the same tenant,
    after a Layer-1 copy the target's values SHALL equal the source's at copy time, and any
    subsequent change to either Page's values SHALL NOT alter the other's.
    """
    # Two SEPARATE Pages (independent stored slices) within the SAME verified tenant.
    source_store = _Store(source_values)
    target_store = _Store(target_values)
    source_svc = _service_over(source_store)
    target_svc = _service_over(target_store)

    # The source's resolved values AT COPY TIME (what the target must equal after the copy).
    source_at_copy_time = source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)

    # Perform the one-time Layer-1 copy via the ACTUAL product method: a copy-service reads the
    # source store's resolved view and writes the snapshot onto the (independent) target store.
    # Same verified tenant; source_page == target_page == the one SAM-owned page (Req 9.4).
    copy_svc = _copy_service(source_store, target_store)
    copy_svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)

    # (1) After the copy, the TARGET equals the SOURCE at copy time (Req 9.1 / 9.3).
    assert target_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == source_at_copy_time

    # ── Independence: a subsequent change to EITHER Page must not alter the other (Req 9.2/9.5) ──

    target_after_copy = target_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)
    source_after_copy = source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)

    # (2) Mutate the SOURCE after the copy → the TARGET is unaffected.
    s_attr, s_val = source_mutation
    source_svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, s_attr, s_val)
    assert target_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == target_after_copy, (
        "a change to the source Page must not alter the target Page"
    )

    # (3) Mutate the TARGET after the copy → the SOURCE is unaffected (compare against the source's
    # state as it is NOW, i.e. after its own mutation in step 2 — the target change still must not
    # reach back into the source).
    source_now = source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)
    t_attr, t_val = target_mutation
    target_svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, t_attr, t_val)
    assert source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == source_now, (
        "a change to the target Page must not alter the source Page"
    )

    # (4) A REMOVE on the target likewise leaves the source untouched.
    source_now2 = source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)
    target_svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, t_attr, None)  # None => REMOVE
    assert source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == source_now2, (
        "removing a target attribute must not alter the source Page"
    )

    # Sanity: nothing leaked the other way — the source's own post-mutation state is intact.
    assert s_attr in source_svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID)
