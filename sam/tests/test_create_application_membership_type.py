"""
application-app task 2.3 — ``membership_type`` on the PUBLIC application path (D21/R11, seam b).

``create_application`` reuses the ``create_member`` spine but the public path is trusted for
NOTHING. Task 2.3 implements the 0.3 decision for ``membership_type``, in two halves keyed on
whether the tenant EXPOSES ``membership_type`` on the form (``application_visible``):

1. **Exposed (R11.2, R4a.3).** The applicant picks from the field's **application subset** (the
   public-safe type codes declared via ``application_choices``), the form pre-selecting the first.
   The server trusts neither the submitted value nor the default: it re-validates the submitted
   value against the subset (``must be one of`` 422 for a value outside it, EVEN IF it is a valid
   staff-facing catalog type) AND still runs the authoritative live-catalog reference check (R11 —
   unknown/retired → 422).
2. **Not exposed (R11.3).** The applicant never supplies a type, so the server stamps the
   **tenant-default** — the first ACTIVE catalog entry in presentation order (the same first-option
   semantics the exposed form pre-selects) — so the ``status=application`` record stays
   catalog-valid. The stamped value passes the live-catalog reference check by construction.

These assert exactly the task 2.3 behaviours; the earlier task 2.2 behaviours (forced status,
privileged strip, session de-dup, un-flatten) are covered in ``test_create_application.py``.

Validates: Requirements R4a.2, R4a.3, R4a.5, R11.2, R11.3, R11.4
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
    VALIDATION_MUST_BE_ONE_OF,
)
from dataclasses import replace

from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface) and
# the shared catalog-entry factory.
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"


# ── overlays: membership_type exposed (with a subset) vs NOT exposed ──────────────────


def _overlay_membership_type_exposed(subset=("gewoon",)) -> TenantOverlay:
    """Put the identity fields + ``membership_type`` on the form, with a public-safe subset.

    The subset is the tenant's PUBLIC-safe type codes — a strict subset of the live catalog
    (``gewoon`` is public, ``erelid`` is staff-only / withheld from the form).
    """
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            # birth_date on the form so the task-2.4 public-path identity requirement (R6.1a) is
            # satisfied on the success path (otherwise create 422s before membership_type logic).
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                application_required=True,
                application_choices=tuple(subset),
            ),
        },
        fields={},
    )


def _overlay_membership_type_not_exposed() -> TenantOverlay:
    """Identity fields on the form, but ``membership_type`` is NOT application-selected."""
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            # membership.membership_type deliberately NOT marked application_visible
        },
        fields={},
    )


def _options_from_catalog(catalog):
    """Fold the catalog vocabulary onto the field's INLINE options (03b CONTRACT, Task 10.5).

    membership_type owns its vocabulary as the field's own ``EnumOption``s now; the catalog is
    retired. The EXPAND fold maps each type to an option (``active`` → ``allowed:true``,
    retired → ``allowed:false``). These tests author that resolved state directly so the public
    create path reads the field's options, not a seeded catalog.
    """
    return tuple(
        EnumOption(
            value=e.type_code,
            label=e.label,
            allowed=e.active,
            order=e.order,
        )
        for e in catalog
    )


def _service(overlay: TenantOverlay, *, catalog) -> MembershipService:
    repo = _ApplicationRepo()
    for entry in catalog:
        repo.add_type(TENANT, entry)
    # Fold the catalog vocabulary onto the membership_type field's inline options so the
    # field-options-only reader (03b CONTRACT) resolves the same values the catalog carried.
    options = _options_from_catalog(catalog)
    mt_key = "membership.membership_type"
    existing = dict(overlay.overrides)
    base = existing.get(mt_key)
    if base is not None:
        existing[mt_key] = replace(base, options=options)
    else:
        existing[mt_key] = FixedFieldOverride(options=options)
    overlay = replace(overlay, overrides=existing)
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
    )


def _identity_body(**over):
    # email + name + birth_date are required on the public path (R6.1/R6.1a, enforced by task
    # 2.4), so a baseline body carries them all for the success-path assertions.
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
    }
    body.update(over)
    return body


#: Affirmative consent. Task 2.6 made consent MANDATORY on the public create path (F4/R12.1);
#: these membership_type tests are not about consent, so `_create` supplies it by default so the
#: consent gate never pre-empts the membership_type assertions (the consent gate itself is pinned
#: in `test_application_consent.py`).
_AFFIRMATIVE_CONSENT = {"accepted": True}


def _create(service, body, **kw):
    """Call ``create_application`` with affirmative consent supplied (task 2.6)."""
    kw.setdefault("consent", _AFFIRMATIVE_CONSENT)
    return service.create_application(TENANT, body, **kw)


# A catalog with a public type (gewoon) and a staff-only type (erelid); both ACTIVE.
def _catalog_two_active():
    return [_entry(TENANT, "gewoon", order=10), _entry(TENANT, "erelid", order=20)]


# ── 1. exposed → submitted subset value re-validated against subset AND catalog ───────


class TestExposedSubsetAccepted:
    def test_submitted_subset_value_is_accepted(self):
        service = _service(
            _overlay_membership_type_exposed(subset=("gewoon",)),
            catalog=_catalog_two_active(),
        )
        body = _identity_body(**{"membership.membership_type": "gewoon"})
        rec = _create(service, body, session_key="s1")
        # In-subset AND a live catalog entry → accepted, stored as submitted.
        assert rec["membership"]["membership_type"] == "gewoon"
        assert rec["membership"]["status"] == "application"


# ── 2. exposed → value OUTSIDE the subset is rejected (even if a valid staff type) ────


class TestExposedNonSubsetRejected:
    def test_value_outside_subset_is_rejected_even_if_valid_staff_type(self):
        # `erelid` is an ACTIVE catalog type but is NOT in the public subset — it must be rejected
        # with a subset `must be one of` error, not accepted (R4a.3).
        service = _service(
            _overlay_membership_type_exposed(subset=("gewoon",)),
            catalog=_catalog_two_active(),
        )
        body = _identity_body(**{"membership.membership_type": "erelid"})
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        err = exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY]
        assert err.code == VALIDATION_MUST_BE_ONE_OF
        # nothing was persisted
        assert len(service._repo.members) == 0


# ── 3. exposed → an in-subset value that is NOT a live catalog entry is rejected (R11) ─


class TestExposedCatalogReferenceStillAuthoritative:
    def test_unknown_catalog_reference_is_rejected(self):
        # The subset ADMITS `ghost`, but it is not in the live catalog → the R11 reference check
        # (unchanged, authoritative) rejects it. The subset gate never weakens the catalog check.
        service = _service(
            _overlay_membership_type_exposed(subset=("ghost",)),
            catalog=_catalog_two_active(),
        )
        body = _identity_body(**{"membership.membership_type": "ghost"})
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert (
            exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
            == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        )
        assert len(service._repo.members) == 0

    def test_retired_catalog_reference_is_rejected(self):
        # `gewoon` is in the subset but RETIRED (active=false) in the catalog → R11 rejects it.
        catalog = [
            _entry(TENANT, "gewoon", order=10, active=False),
            _entry(TENANT, "erelid", order=20),
        ]
        service = _service(
            _overlay_membership_type_exposed(subset=("gewoon",)), catalog=catalog
        )
        body = _identity_body(**{"membership.membership_type": "gewoon"})
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert (
            exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code == MEMBERSHIP_TYPE_RETIRED
        )
        assert len(service._repo.members) == 0


# ── 4. NOT exposed → tenant-default stamped server-side, catalog-valid ────────────────


class TestNotExposedTenantDefaultStamp:
    def test_tenant_default_is_stamped_when_not_exposed(self):
        # The applicant never supplies a type; the server stamps the FIRST active catalog entry
        # in presentation order (`gewoon` at order=10, ahead of `erelid` at order=20).
        service = _service(
            _overlay_membership_type_not_exposed(), catalog=_catalog_two_active()
        )
        rec = _create(service, _identity_body(), session_key="s1")
        assert rec["membership"]["membership_type"] == "gewoon"
        assert rec["membership"]["status"] == "application"

    def test_stamped_default_follows_presentation_order(self):
        # Catalog declared out of order → the LOWEST `order` wins (presentation order), not insert
        # order: `basis` (order=5) is the default even though `premium` (order=50) was added first.
        catalog = [
            _entry(TENANT, "premium", order=50),
            _entry(TENANT, "basis", order=5),
        ]
        service = _service(_overlay_membership_type_not_exposed(), catalog=catalog)
        rec = _create(service, _identity_body(), session_key="s1")
        assert rec["membership"]["membership_type"] == "basis"

    def test_default_skips_retired_entries(self):
        # The first ACTIVE entry is the default — a retired entry ahead of it in order is skipped.
        catalog = [
            _entry(TENANT, "oud", order=1, active=False),
            _entry(TENANT, "gewoon", order=10),
        ]
        service = _service(_overlay_membership_type_not_exposed(), catalog=catalog)
        rec = _create(service, _identity_body(), session_key="s1")
        assert rec["membership"]["membership_type"] == "gewoon"

    def test_empty_catalog_surfaces_unknown_reference_not_a_dangling_record(self):
        # A tenant with an EMPTY catalog has no default to stamp. The record must NOT be persisted
        # with a missing/dangling type — the fixed-field required rule rejects the absent reference
        # (R11.4: the public path never persists a dangling type).
        service = _service(_overlay_membership_type_not_exposed(), catalog=[])
        with pytest.raises(MemberValidationError):
            _create(service, _identity_body(), session_key="s1")
        assert len(service._repo.members) == 0
