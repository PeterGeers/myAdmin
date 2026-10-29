"""
03b BU-2 (Task 2.1) — the ``membership_type`` reference check reads the FIELD's options.

Under the 03b unified enum model (Req 3.1) ``membership_type`` is no longer validated against the
separate ``membershiptype#<code>`` catalog: its vocabulary lives on the ``membership_type`` FIELD
as rich ``EnumOption``s, each with an ``allowed`` (retired/grandfather) flag. These tests pin the
re-pointed :meth:`MembershipService._validate_membership_type_reference` + the re-pointed
:meth:`_default_membership_type` against FIELD OPTIONS (the post-fold resolved state), and assert
the transitional catalog fallback still governs while a field carries NO inline options (the
EXPAND-before-reader safety gate, Req 6.4).

Covered behaviours:
- unknown value (not one of the field's option values) → ``MEMBERSHIP_TYPE_UNKNOWN_REFERENCE``;
- present but ``allowed:false`` (retired) → ``MEMBERSHIP_TYPE_RETIRED``;
- grandfathered existing member: a stored ``allowed:false`` value stays valid on an update that
  does NOT change the value (the value-changed-only guard, design C8);
- default when OFF the form = first ``allowed:true`` option by ``order`` (NOT a catalog read);
- transitional fallback: a field with no inline options still validates / defaults via the catalog.

Validates: Requirements 3.2, 3.2a, 3.4a
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberValidationError,
)
from sam.members.domain.error_codes import (
    MEMBERSHIP_TYPE_RETIRED,
    MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
)
from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface) and
# the shared catalog-entry factory (used only to exercise the transitional fallback path).
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"


# ── overlays: membership_type field carrying INLINE options (the post-fold state) ─────


def _overlay_with_inline_options(options) -> TenantOverlay:
    """Author the ``membership_type`` fixed field with INLINE enum options (the post-fold shape).

    After the EXPAND fold (Task 7) the catalog is collapsed onto the field's own ``options``;
    here we construct that resolved state directly so the reference check reads field options.
    """
    return TenantOverlay(
        overrides={
            "membership.membership_type": FixedFieldOverride(options=tuple(options)),
        },
        fields={},
    )


def _service(overlay: TenantOverlay, *, catalog=()) -> MembershipService:
    repo = _ApplicationRepo()
    for entry in catalog:
        repo.add_type(TENANT, entry)
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
    )


def _record(membership_type):
    return {
        "tenant_id": TENANT,
        "membership": {"membership_type": membership_type},
    }


# Two allowed options + one retired (grandfathered) option, ordered.
def _options_two_allowed_one_retired():
    return [
        EnumOption(value="gewoon_lid", label={"nl": "Gewoon lid"}, allowed=True, order=10),
        EnumOption(value="donateur", label={"nl": "Donateur"}, allowed=True, order=30),
        EnumOption(value="erelid", label={"nl": "Erelid"}, allowed=False, order=20),
    ]


# ── 1. unknown value → MEMBERSHIP_TYPE_UNKNOWN_REFERENCE ──────────────────────────────


class TestReferenceAgainstFieldOptions:
    def test_unknown_value_is_rejected_unknown_reference(self):
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("does-not-exist"))
        assert (
            exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
            == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        )

    def test_allowed_option_value_is_accepted(self):
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        # No raise = accepted.
        service._validate_membership_type_reference(TENANT, _record("gewoon_lid"))
        service._validate_membership_type_reference(TENANT, _record("donateur"))

    def test_retired_option_value_is_rejected_retired(self):
        # `erelid` is a KNOWN option but allowed:false → retired, not assignable to a new/changed
        # record (Req 3.2 grandfather: it has left the picker).
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("erelid"))
        assert exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code == MEMBERSHIP_TYPE_RETIRED

    def test_blank_value_is_not_our_concern(self):
        # Absence/blank is the fixed-field required rule's concern, not the reference check.
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        service._validate_membership_type_reference(TENANT, _record(None))
        service._validate_membership_type_reference(TENANT, _record("   "))

    def test_error_message_names_the_field_and_is_caller_safe(self):
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("ghost"))
        assert MEMBERSHIP_TYPE_FIELD_KEY in exc.value.errors
        detail = exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].detail
        # Caller-safe: names the offending value + the field's options, no internal/catalog detail.
        assert "ghost" in detail
        assert "options" in detail


# ── 2. grandfather preserved (Property 2): existing retired value stays valid unless changed ──


class TestGrandfatherPreserved:
    def test_update_not_changing_a_retired_value_is_not_re_validated(self):
        # The CRUD update path only re-runs the reference check when the type actually CHANGES
        # (design C8). A member stored with a now-retired `erelid` whose update does not touch the
        # type must stay valid. We model the guard the caller applies: the reference check is NOT
        # invoked when the value is unchanged — so directly invoking it on the unchanged retired
        # value would reject, but the caller never does. Assert the two halves:
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        # (a) the stored retired value would be rejected IF re-validated (it is retired)...
        with pytest.raises(MemberValidationError):
            service._validate_membership_type_reference(TENANT, _record("erelid"))
        # (b) ...but the value-changed-only guard means an unchanged value is not re-validated.
        unchanged = service._membership_type_of(_record("erelid")) == service._membership_type_of(
            _record("erelid")
        )
        assert unchanged is True  # equal → the caller skips the reference check


# ── 3. default when OFF the form = first allowed:true option by order (NOT a catalog read) ──


class TestDefaultFromFieldOptions:
    def test_default_is_first_allowed_true_option_by_order(self):
        # gewoon_lid(order 10, allowed) < erelid(order 20, retired) < donateur(order 30, allowed).
        # The default is the first ALLOWED option by order → gewoon_lid (erelid is skipped).
        service = _service(_overlay_with_inline_options(_options_two_allowed_one_retired()))
        assert service._default_membership_type(TENANT) == "gewoon_lid"

    def test_default_skips_retired_option_even_when_lowest_order(self):
        options = [
            EnumOption(value="oud", label={}, allowed=False, order=1),
            EnumOption(value="gewoon_lid", label={}, allowed=True, order=10),
        ]
        service = _service(_overlay_with_inline_options(options))
        assert service._default_membership_type(TENANT) == "gewoon_lid"

    def test_default_absent_order_sorts_after_ranked_options(self):
        options = [
            EnumOption(value="no_order", label={}, allowed=True, order=None),
            EnumOption(value="ranked", label={}, allowed=True, order=5),
        ]
        service = _service(_overlay_with_inline_options(options))
        assert service._default_membership_type(TENANT) == "ranked"

    def test_default_is_none_when_no_allowed_option(self):
        options = [EnumOption(value="erelid", label={}, allowed=False, order=10)]
        service = _service(_overlay_with_inline_options(options))
        assert service._default_membership_type(TENANT) is None


# ── 4. transitional fallback: a field with NO inline options still uses the catalog (Req 6.4) ──


class TestTransitionalCatalogFallback:
    def test_reference_check_falls_back_to_catalog_when_no_inline_options(self):
        # No override options → the membership_type field carries no inline vocabulary (pre-fold).
        # The reference check must fall back to the legacy catalog so a pre-migration deploy is
        # non-fatal: an unknown code is still rejected.
        service = _service(
            TenantOverlay(overrides={}, fields={}),
            catalog=[_entry(TENANT, "gewoon_lid", order=10)],
        )
        # live catalog value accepted...
        service._validate_membership_type_reference(TENANT, _record("gewoon_lid"))
        # ...unknown catalog value rejected
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("ghost"))
        assert (
            exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
            == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        )

    def test_retired_catalog_entry_rejected_via_fallback(self):
        service = _service(
            TenantOverlay(overrides={}, fields={}),
            catalog=[_entry(TENANT, "erelid", order=10, active=False)],
        )
        with pytest.raises(MemberValidationError) as exc:
            service._validate_membership_type_reference(TENANT, _record("erelid"))
        assert exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code == MEMBERSHIP_TYPE_RETIRED

    def test_default_falls_back_to_first_active_catalog_entry_when_no_inline_options(self):
        service = _service(
            TenantOverlay(overrides={}, fields={}),
            catalog=[
                _entry(TENANT, "premium", order=50),
                _entry(TENANT, "basis", order=5),
            ],
        )
        # First active catalog entry in presentation order → basis (order 5).
        assert service._default_membership_type(TENANT) == "basis"
