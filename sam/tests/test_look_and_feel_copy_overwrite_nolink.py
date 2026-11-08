"""
SAM Page Look-and-Feel — Task 5.5: ``LookAndFeelSettingsService.copy_settings`` — the remaining
copy UNIT tests that pin OVERWRITE of a pre-populated target, NO-LINK after copy, and the
cross-tenant → caller-safe 403 mapping (Req 9.2 / 9.3 / 9.4 / 9.5).

Spec: ``.kiro/specs/Members/15 - sam-page-look-and-feel`` (design C3 / DD-2, Layer 1).

Relationship to the other copy tests (no duplication)
-----------------------------------------------------
- ``test_look_and_feel_copy_settings.py`` (task 5.3) already pins the happy path + the "no read /
  no write on cross-tenant" angle via a RecordingWriter that only captures op shapes.
- ``test_look_and_feel_copy_settings_props.py`` (task 5.4) owns Property 9. This file does NOT
  touch that file.

Task 5.5 adds the BEHAVIOURAL angle the op-shape recording in 5.3 does not reach — a STATEFUL fake
store (shared by the reader and writer, so a copy observably mutates what a later read returns):

- OVERWRITE (Req 9.3): a target that already holds prior values has those values REPLACED WHOLESALE
  by the source snapshot — the copy is a whole-slice ``SET look_and_feel = :snapshot``, not a
  per-key merge, so a target-only key present before the copy is GONE afterwards.
- NO-LINK (Req 9.2 / 9.5): after the copy, changing the SOURCE does not alter the TARGET, and
  changing the TARGET does not alter the SOURCE — the two Pages are independent, nothing propagates.
- Cross-tenant → caller-safe 403 (Req 9.4): the rejection is a ``PermissionError`` (the edge's 403
  branch), is distinct from the validation 422 type, carries a generic message that does not confirm
  the other tenant/page exists, and leaves BOTH tenants' stored state untouched.

The reader/writer are in-memory fakes (no boto3, no DynamoDB — pure domain, steering 35/39). The
store is keyed by ``(tenant_id, page_id)`` so a later generalization to more page types would slot
in without rewriting the test; today both resolve to the one application-form slice.

Validates: Requirements 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.look_and_feel_settings_service import (
    APPLICATION_FORM_PAGE_ID,
    CrossTenantCopyError,
    LookAndFeelSettingsService,
    LookAndFeelValidationError,
)

_TENANT = "h-dcn"
_OTHER_TENANT = "t-other"


# ── Stateful in-memory store shared by the reader + writer (no boto3) ────────────────────


class FakeSlotStore:
    """A tiny stateful stand-in for the ``look_and_feel`` slice, keyed by tenant.

    The reader and the writer share ONE of these, so a copy/set issued through the writer is
    observable on a subsequent read — exactly what pins OVERWRITE (the slice is replaced wholesale)
    and NO-LINK (a later change to one tenant's/page's slice does not touch another's) behaviourally
    rather than by inspecting recorded op shapes (that angle is task 5.3's).

    Today both source and target resolve to the single application-form page, so a per-tenant slot
    is sufficient; the store is kept minimal rather than modelling a page dimension that does not
    exist yet (steering 37 — no speculative generality).
    """

    def __init__(self, initial=None):
        self._slots: dict[str, dict] = {
            tenant: dict(values) for tenant, values in (initial or {}).items()
        }

    # Reader seam -----------------------------------------------------------------------
    def get_look_and_feel(self, tenant_id):
        return dict(self._slots.get(tenant_id, {}))

    # Writer seam -----------------------------------------------------------------------
    def set_look_and_feel(self, tenant_id, attribute, value, *, client_op_id=None):
        self._slots.setdefault(tenant_id, {})[attribute] = value
        return {"version": "v-next", "idempotent_replay": False}

    def remove_look_and_feel(self, tenant_id, attribute, *, client_op_id=None):
        self._slots.get(tenant_id, {}).pop(attribute, None)
        return {"version": "v-next", "idempotent_replay": False}

    def copy_look_and_feel(self, tenant_id, snapshot_values, *, client_op_id=None):
        # Whole-slice SET look_and_feel = :snapshot — REPLACE, not merge (Req 9.3).
        self._slots[tenant_id] = dict(snapshot_values)
        return {"version": "v-next", "idempotent_replay": False}

    # Test introspection ----------------------------------------------------------------
    def slot(self, tenant_id):
        return dict(self._slots.get(tenant_id, {}))


def _service_over(store):
    """Build a service whose reader and writer are both backed by the SAME stateful store."""
    return LookAndFeelSettingsService(store, store)


# ── OVERWRITE — a pre-populated target is replaced wholesale, not merged (Req 9.3) ───────


def test_copy_settings_overwrites_prepopulated_target_wholesale():
    # Same tenant, same page today: the "source" snapshot is the tenant's current resolved slice.
    # Seed the slice with prior values that the copy must replace wholesale.
    store = FakeSlotStore(
        {
            _TENANT: {
                "color_primary": "#111111",
                "font_body": "Inter",
                "shadow_style": "dramatic",
            }
        }
    )
    svc = _service_over(store)

    # A snapshot copy within the tenant re-SETs the slice to the (same-tenant) source values —
    # the whole slice is written as one unit, so there is no leftover from a prior value set.
    svc.copy_settings(_TENANT, APPLICATION_FORM_PAGE_ID, APPLICATION_FORM_PAGE_ID)

    # Slice equals the snapshot exactly — nothing extra, nothing merged in from a prior state.
    assert store.slot(_TENANT) == {
        "color_primary": "#111111",
        "font_body": "Inter",
        "shadow_style": "dramatic",
    }


def test_copy_settings_empty_source_overwrites_target_to_all_defaults():
    # OVERWRITE semantics at the "clear" extreme: an EMPTY source snapshot replaces whatever the
    # target held with the empty slice (→ Layer-2 defaults). Any pre-existing target key must be
    # GONE afterwards. Model source + target as two tenants sharing one store: the source tenant
    # has no slice (empty snapshot), the target tenant is pre-populated.
    store = FakeSlotStore(
        {
            _TENANT: {"color_primary": "#ABCDEF", "base_spacing": "relaxed"},  # target pre-populated
            # _OTHER_TENANT (the source) has NO slice → empty snapshot
        }
    )

    # The empty source snapshot overwrites the pre-populated target via the whole-slice SET.
    source_snapshot = store.get_look_and_feel(_OTHER_TENANT)
    assert source_snapshot == {}
    store.copy_look_and_feel(_TENANT, source_snapshot)

    # Target slice is now empty — the prior keys are gone, not merged with (→ all Layer-2 defaults).
    assert store.slot(_TENANT) == {}


def test_copy_settings_replaces_not_merges_dropping_target_only_keys():
    # The sharpest overwrite assertion: a key present in the TARGET but NOT in the SOURCE snapshot
    # must be DROPPED (a merge would keep it). Source and target are two tenants sharing one store.
    store = FakeSlotStore(
        {
            _OTHER_TENANT: {"color_primary": "#222222", "font_heading": "Inter"},  # source
            _TENANT: {"shadow_style": "subtle"},  # target: a DIFFERENT, target-only key
        }
    )

    source_snapshot = store.get_look_and_feel(_OTHER_TENANT)

    # Whole-slice SET of the source snapshot onto the target drops the target-only key (Req 9.3).
    store.copy_look_and_feel(_TENANT, source_snapshot)

    assert store.slot(_TENANT) == {"color_primary": "#222222", "font_heading": "Inter"}
    assert "shadow_style" not in store.slot(_TENANT)


# ── NO-LINK — after the copy the two Pages are independent (Req 9.2 / 9.5) ────────────────


def test_copy_settings_no_link_source_change_does_not_touch_target():
    # Two tenants model two independent Pages sharing one store. Copy the source tenant's slice onto
    # the target tenant, then change the SOURCE — the TARGET must not move (no ongoing link).
    store = FakeSlotStore({_OTHER_TENANT: {"color_primary": "#2D5F8A"}})

    # Perform the overwrite onto the target tenant via the writer's whole-slice SET (the copy op).
    source_snapshot = store.get_look_and_feel(_OTHER_TENANT)
    store.copy_look_and_feel(_TENANT, source_snapshot)
    assert store.slot(_TENANT) == {"color_primary": "#2D5F8A"}

    # Change the SOURCE after the copy — a later edit to the source Page.
    svc = _service_over(store)
    svc.set_setting(_OTHER_TENANT, APPLICATION_FORM_PAGE_ID, "color_primary", "#000000")

    # The TARGET is unchanged: nothing is wired to propagate the source's later change.
    assert store.slot(_TENANT) == {"color_primary": "#2D5F8A"}
    assert store.slot(_OTHER_TENANT) == {"color_primary": "#000000"}


def test_copy_settings_no_link_target_change_does_not_touch_source():
    # Symmetric direction: after the copy, changing the TARGET must not alter the SOURCE.
    store = FakeSlotStore({_OTHER_TENANT: {"font_body": "Inter"}})
    source_snapshot = store.get_look_and_feel(_OTHER_TENANT)
    store.copy_look_and_feel(_TENANT, source_snapshot)

    svc = _service_over(store)
    svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, "font_body", "system")

    # The SOURCE is unchanged — the copy left no inheritance from target back to source.
    assert store.slot(_OTHER_TENANT) == {"font_body": "Inter"}
    assert store.slot(_TENANT) == {"font_body": "system"}


# ── Cross-tenant source → caller-safe 403 mapping (Req 9.4) ──────────────────────────────


def test_copy_settings_cross_tenant_maps_to_caller_safe_403_permission_error():
    # The cross-tenant rejection is a PermissionError (the edge's 403 branch), NOT a validation
    # error (422). Keeping the two as distinct types is what lets the edge map each to its own
    # caller-safe status without inspecting the message.
    store = FakeSlotStore({_TENANT: {"base_spacing": "normal"}, _OTHER_TENANT: {"base_spacing": "relaxed"}})
    svc = _service_over(store)

    with pytest.raises(CrossTenantCopyError) as exc:
        svc.copy_settings(
            _TENANT,
            APPLICATION_FORM_PAGE_ID,
            APPLICATION_FORM_PAGE_ID,
            source_tenant_id=_OTHER_TENANT,
        )

    err = exc.value
    assert isinstance(err, PermissionError)  # → 403 branch at the edge
    assert not isinstance(err, LookAndFeelValidationError)  # NOT the 422 (validation) branch
    # Generic, caller-safe message: must not confirm whether the other tenant/page exists.
    assert _OTHER_TENANT not in str(err)


def test_copy_settings_cross_tenant_leaves_both_tenants_state_untouched():
    # The 403 fires BEFORE any read or write, so neither tenant's stored slice is observed or
    # mutated — asserted here on the STATEFUL store (5.3 asserts the same via op-shape recording).
    store = FakeSlotStore(
        {_TENANT: {"base_spacing": "normal"}, _OTHER_TENANT: {"base_spacing": "relaxed"}}
    )
    svc = _service_over(store)

    with pytest.raises(CrossTenantCopyError):
        svc.copy_settings(
            _TENANT,
            APPLICATION_FORM_PAGE_ID,
            APPLICATION_FORM_PAGE_ID,
            source_tenant_id=_OTHER_TENANT,
        )

    # Both slices are exactly as seeded — no overwrite, no partial change.
    assert store.slot(_TENANT) == {"base_spacing": "normal"}
    assert store.slot(_OTHER_TENANT) == {"base_spacing": "relaxed"}
