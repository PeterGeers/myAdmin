"""
application-app task 2.4 — required-ness enforcement on the PUBLIC ``create_application`` path.

Task 2.4 closes the required-ness gap the authenticated chain leaves (R6/R6.6, R4b): the public
path must server-enforce EVERY required field — platform-``required`` AND the FORM-ONLY
``application_required`` overlay (R4b) — PLUS the public-path identity tightening (email + name +
DOB required regardless of config, R6.1/R6.1a), run the EMAIL/IBAN format checks (email
required+valid; IBAN mod-97 only WHEN the incasso payment field is shown — the task 3.4
FieldFormat step, gated by ``show_when``), keep ``tussenvoegsel`` (``name_infix``) OPTIONAL, and
COLLECT every problem into ONE R1a 422 ``errors`` map (not fail-on-first, R6.5).

These assert exactly the task 2.4 behaviours; task 2.2/2.3/2.6 behaviours (forced status, strip,
session de-dup, membership_type, consent) live in their own suites. The generic FieldFormat step
itself is unit-pinned in ``test_field_format_enforcement.py`` (task 3.4); here we assert it is
WIRED into the public create path (email + conditional IBAN).

Validates: Requirements R6, R6.1, R6.1a, R6.5, R6.6, R4b.2, R4b.3, R4b.4, R4b.5
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain._membership_errors import MemberValidationError
from sam.members.domain.error_codes import (
    VALIDATION_INVALID_EMAIL,
    VALIDATION_INVALID_IBAN,
    VALIDATION_REQUIRED,
)
from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.field_resolver import (
    FieldFormat,
    FixedFieldOverride,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface) and
# the shared catalog-entry factory.
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"

VALID_IBAN = "NL91ABNA0417164300"
INVALID_IBAN = "NL00ABNA0417164300"

_AFFIRMATIVE_CONSENT = {"accepted": True}


# ── overlay: identity fields + an application-required overlay field + a conditional IBAN ──


def _overlay() -> TenantOverlay:
    """Put the identity + an application-required overlay field + a show_when-gated IBAN on form.

    - ``personal.first_name`` / ``personal.last_name`` / ``personal.email`` / ``personal.birth_date``
      / ``personal.name_infix`` → fixed-field overrides, application-visible. ``email`` carries the
      EMAIL format checker (R7/R6.1). ``name_infix`` (tussenvoegsel) is visible but NOT
      application-required → must accept a blank value (R4b.2).
    - ``personal.payment_method`` → a selector that drives the IBAN ``show_when``.
    - ``personal.iban`` → application-visible, IBAN format checker, shown ONLY when
      ``payment_method == 'incasso'`` (R6.2/R6.3 — IBAN mod-97 only when incasso is chosen).
    - an overlay field ``emergency_contact`` → application-visible AND ``application_required``
      (the FORM-ONLY tightening, R4b): blank → required error even though it is not platform-required.
    - ``membership.membership_type`` → on the form so a valid applicant can pick a type.
    """
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.name_infix": FixedFieldOverride(application_visible=True),
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(
                application_visible=True, format=FieldFormat(checker="EMAIL")
            ),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                # 03b CONTRACT (Task 10.5): membership_type owns its vocabulary as INLINE options.
                options=(
                    EnumOption(value='gewoon', label={"nl": 'Gewoon', "en": 'Gewoon'}, allowed=True, order=10),
                    EnumOption(value='erelid', label={"nl": 'Erelid', "en": 'Erelid'}, allowed=True, order=20),
                ),
            ),
        },
        fields={
            "payment_method": OverlayField(
                key="payment_method",
                type=FieldType.ENUM,
                choices=("bank", "incasso"),
                label={"nl": "Betaalwijze", "en": "Payment method"},
                application_visible=True,
            ),
            "iban": OverlayField(
                key="iban",
                type=FieldType.STRING,
                label={"nl": "IBAN", "en": "IBAN"},
                application_visible=True,
                format=FieldFormat(checker="IBAN"),
                show_when={"payment_method": "incasso"},
            ),
            "emergency_contact": OverlayField(
                key="emergency_contact",
                type=FieldType.STRING,
                label={"nl": "Noodcontact", "en": "Emergency contact"},
                application_visible=True,
                application_required=True,  # form-only tightening (R4b)
            ),
        },
    )


@pytest.fixture()
def service() -> MembershipService:
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay()})
    )


def _submission(**over):
    """A VALID public submission with every required field present (payment=bank → no IBAN)."""
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
        "membership.membership_type": "gewoon",
        "overlay.payment_method": "bank",
        "overlay.emergency_contact": "Alex 06-12345678",
    }
    body.update(over)
    return body


def _create(service, body, **kw):
    return service.create_application(
        TENANT, body, consent=_AFFIRMATIVE_CONSENT, **kw
    )


def _errors(excinfo) -> dict:
    return excinfo.value.errors


# ── a fully-valid submission goes through (baseline) ──────────────────────────────────


def test_valid_submission_with_all_required_fields_succeeds(service):
    rec = _create(service, _submission(), session_key="s1")
    assert rec["membership"]["status"] == "application"
    assert rec["personal"]["email"] == "sam@example.com"


# ── 1. all required fields server-enforced (platform + application-required) ──────────


class TestAllRequiredEnforced:
    def test_missing_platform_required_last_name_is_rejected(self, service):
        body = _submission()
        del body["personal.last_name"]
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "personal.last_name" in _errors(exc)
        assert _errors(exc)["personal.last_name"].code == VALIDATION_REQUIRED

    def test_missing_application_required_overlay_field_is_rejected(self, service):
        # `emergency_contact` is NOT platform-required — it is required ONLY because the tenant
        # marked it application_required on the form (R4b.2). A blank must still be rejected.
        body = _submission()
        del body["overlay.emergency_contact"]
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "overlay.emergency_contact" in _errors(exc)
        assert _errors(exc)["overlay.emergency_contact"].code == VALIDATION_REQUIRED

    def test_blank_application_required_overlay_field_is_rejected(self, service):
        body = _submission(**{"overlay.emergency_contact": "   "})
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "overlay.emergency_contact" in _errors(exc)

    def test_missing_date_of_birth_is_rejected(self, service):
        # DOB is required on the public path (R6.1a) though platform-optional generally.
        body = _submission()
        del body["personal.birth_date"]
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "personal.birth_date" in _errors(exc)
        assert _errors(exc)["personal.birth_date"].code == VALIDATION_REQUIRED


# ── 2. email required + valid (public-path tightening) ────────────────────────────────


class TestEmailRequiredAndValid:
    def test_missing_email_is_rejected_required(self, service):
        # email is platform-OPTIONAL generally; the public path requires it (R6.1).
        body = _submission()
        del body["personal.email"]
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "personal.email" in _errors(exc)
        assert _errors(exc)["personal.email"].code == VALIDATION_REQUIRED

    def test_blank_email_is_rejected_required(self, service):
        with pytest.raises(MemberValidationError) as exc:
            _create(service, _submission(**{"personal.email": "  "}), session_key="s1")
        assert "personal.email" in _errors(exc)

    def test_malformed_email_is_rejected_invalid_format(self, service):
        # Present but not a well-formed address → the EMAIL FieldFormat checker fires (R7 wired).
        with pytest.raises(MemberValidationError) as exc:
            _create(service, _submission(**{"personal.email": "not-an-email"}), session_key="s1")
        assert _errors(exc)["personal.email"].code == VALIDATION_INVALID_EMAIL

    def test_valid_email_passes(self, service):
        rec = _create(service, _submission(**{"personal.email": "ok@domain.org"}), session_key="s1")
        assert rec["personal"]["email"] == "ok@domain.org"


# ── 3. IBAN mod-97 ONLY when the incasso field is shown (R6.2/R6.3) ───────────────────


class TestConditionalIban:
    def test_invalid_iban_rejected_when_incasso_chosen(self, service):
        body = _submission(
            **{"overlay.payment_method": "incasso", "overlay.iban": INVALID_IBAN}
        )
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert _errors(exc)["overlay.iban"].code == VALIDATION_INVALID_IBAN

    def test_valid_iban_accepted_when_incasso_chosen(self, service):
        body = _submission(
            **{"overlay.payment_method": "incasso", "overlay.iban": VALID_IBAN}
        )
        rec = _create(service, body, session_key="s1")
        assert rec["overlay"]["iban"] == VALID_IBAN

    def test_invalid_iban_ignored_when_incasso_not_chosen(self, service):
        # payment_method=bank → the iban field is hidden by show_when → NOT format-checked
        # (R6.3). An invalid IBAN riding along is simply not validated (and not required).
        body = _submission(
            **{"overlay.payment_method": "bank", "overlay.iban": INVALID_IBAN}
        )
        rec = _create(service, body, session_key="s1")
        assert rec["membership"]["status"] == "application"


# ── 4. tussenvoegsel (name_infix) stays OPTIONAL ──────────────────────────────────────


class TestTussenvoegselOptional:
    def test_blank_name_infix_is_accepted(self, service):
        # A shown-but-not-application-required field accepts a blank value (R4b.2) — the whole
        # point of the per-field flag (a Dutch surname infix is legitimately empty).
        rec = _create(service, _submission(**{"personal.name_infix": ""}), session_key="s1")
        assert rec["membership"]["status"] == "application"

    def test_omitted_name_infix_is_accepted(self, service):
        body = _submission()
        body.pop("personal.name_infix", None)  # never submitted at all
        rec = _create(service, body, session_key="s1")
        assert rec["membership"]["status"] == "application"


# ── 5. multiple errors COLLECTED into one 422 (not fail-on-first, R6.5) ───────────────


class TestErrorsCollected:
    def test_multiple_problems_surface_in_one_error_map(self, service):
        # Missing email + missing DOB + missing application-required overlay field + an invalid
        # IBAN (incasso chosen) must ALL appear in a SINGLE MemberValidationError (R6.5) — the
        # applicant sees every problem at once, not one-at-a-time.
        body = _submission(
            **{"overlay.payment_method": "incasso", "overlay.iban": INVALID_IBAN}
        )
        del body["personal.email"]
        del body["personal.birth_date"]
        del body["overlay.emergency_contact"]
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        keys = set(_errors(exc))
        assert {
            "personal.email",
            "personal.birth_date",
            "overlay.emergency_contact",
            "overlay.iban",
        } <= keys

    def test_no_record_written_on_validation_failure(self, service):
        body = _submission()
        del body["personal.email"]
        with pytest.raises(MemberValidationError):
            _create(service, body, session_key="s1")
        # The reject happens before save_member → no applicant record persisted.
        assert len(service._repo.members) == 0
