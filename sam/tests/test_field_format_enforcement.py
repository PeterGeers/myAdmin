"""
Member Application Form (application-app) — task 3.4 tests.

Pins the ONE generic FieldFormat enforcement step added to the authoritative member-record
validator (`WritesMixin._validate_field_formats`, design seam c / §5; R7.4/R7.5). This is the
REUSABLE step the authenticated create/update path (`_validate_member_record`) runs today and
the public `create_application` validator (task 2.4) will call directly — so it is unit-tested
here against a hand-built resolved config, independent of the full service wiring.

Behaviour pinned (R7.4/R7.5):
  * a field carrying a `format` whose value is PRESENT and whose `show_when` HOLDS runs the
    registry checker and MERGES the returned FieldError into the shared `{dotted_key: error}` map;
  * a field HIDDEN by an unmet `show_when` is neither required nor format-checked (skipped);
  * an ABSENT/blank value is left to the required-ness rules (format not run);
  * a valid value produces NO error;
  * an unknown/stray `format.checker` token degrades to "not enforced" (never crashes — R7.3/R7.5);
  * errors from format checking merge ALONGSIDE pre-existing errors in the map.

Validates: Requirements R7.4, R7.5
"""

from __future__ import annotations

from sam.members.domain._membership_writes import WritesMixin
from sam.members.domain.error_codes import (
    VALIDATION_INVALID_EMAIL,
    VALIDATION_INVALID_IBAN,
    VALIDATION_REQUIRED,
    FieldError,
)
from sam.members.domain.field_resolver import (
    FieldConfig,
    FieldFormat,
    FieldOrigin,
    ResolvedField,
)
from sam.members.domain.fixed_fields import FieldType

# A valid NL IBAN (ABN AMRO test IBAN) and an invalid one (checksum fails).
VALID_IBAN = "NL91ABNA0417164300"
INVALID_IBAN = "NL00ABNA0417164300"


def _field(
    key: str,
    group: str,
    *,
    fmt: FieldFormat | None,
    show_when=None,
    field_type: FieldType = FieldType.STRING,
) -> ResolvedField:
    return ResolvedField(
        key=key,
        group=group,
        type=field_type,
        required=False,
        origin=FieldOrigin.FIXED if group != "overlay" else FieldOrigin.VARIABLE,
        show_when=show_when,
        format=fmt,
    )


def _config(*fields: ResolvedField) -> FieldConfig:
    return FieldConfig(tenant_id="h-dcn", fields=tuple(fields))


def _validate(config: FieldConfig, record: dict) -> dict[str, FieldError]:
    errors: dict[str, FieldError] = {}
    WritesMixin._validate_field_formats(config, record, errors)
    return errors


# ── Format runs when the field is shown + present (R7.5) ──────────────────────────────


class TestFormatRunsWhenShown:
    def test_invalid_email_present_and_shown_merges_error(self):
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="EMAIL")))
        errors = _validate(config, {"personal": {"email": "not-an-email"}})
        assert "personal.email" in errors
        assert errors["personal.email"].code == VALIDATION_INVALID_EMAIL

    def test_valid_email_present_and_shown_produces_no_error(self):
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="EMAIL")))
        errors = _validate(config, {"personal": {"email": "applicant@example.org"}})
        assert errors == {}

    def test_invalid_iban_present_and_shown_merges_error(self):
        config = _config(_field("iban", "personal", fmt=FieldFormat(checker="IBAN")))
        errors = _validate(config, {"personal": {"iban": INVALID_IBAN}})
        assert "personal.iban" in errors
        assert errors["personal.iban"].code == VALIDATION_INVALID_IBAN

    def test_valid_iban_present_and_shown_produces_no_error(self):
        config = _config(_field("iban", "personal", fmt=FieldFormat(checker="IBAN")))
        errors = _validate(config, {"personal": {"iban": VALID_IBAN}})
        assert errors == {}

    def test_format_runs_for_an_overlay_field_too(self):
        # Overlay (VARIABLE) fields carry a format just like fixed fields; the step is generic.
        config = _config(_field("contact_email", "overlay", fmt=FieldFormat(checker="EMAIL")))
        errors = _validate(config, {"overlay": {"contact_email": "bad"}})
        assert "overlay.contact_email" in errors


# ── Hidden by show_when → neither required nor format-checked (R7.4) ───────────────────


class TestHiddenFieldSkipped:
    def test_hidden_field_with_invalid_value_is_not_format_checked(self):
        # `iban` is only shown when payment_method == 'incasso'. The record chooses 'bank', so
        # the iban field is hidden → its (invalid) value is NOT format-checked (R6.3/R7.4).
        config = _config(
            _field(
                "iban",
                "personal",
                fmt=FieldFormat(checker="IBAN"),
                show_when={"payment_method": "incasso"},
            )
        )
        record = {"personal": {"payment_method": "bank", "iban": INVALID_IBAN}}
        assert _validate(config, record) == {}

    def test_shown_field_with_invalid_value_is_format_checked(self):
        # Same field, but now the condition HOLDS → the invalid IBAN IS caught (R7.4).
        config = _config(
            _field(
                "iban",
                "personal",
                fmt=FieldFormat(checker="IBAN"),
                show_when={"payment_method": "incasso"},
            )
        )
        record = {"personal": {"payment_method": "incasso", "iban": INVALID_IBAN}}
        errors = _validate(config, record)
        assert errors["personal.iban"].code == VALIDATION_INVALID_IBAN

    def test_field_with_no_show_when_is_always_checked(self):
        # A `None` show_when means "always shown" → the format always runs.
        config = _config(
            _field("email", "personal", fmt=FieldFormat(checker="EMAIL"), show_when=None)
        )
        assert "personal.email" in _validate(config, {"personal": {"email": "bad"}})


# ── Absent / blank value → left to required-ness, format not run ──────────────────────


class TestAbsentValueSkipped:
    def test_absent_value_is_not_format_checked(self):
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="EMAIL")))
        assert _validate(config, {"personal": {}}) == {}

    def test_blank_string_value_is_not_format_checked(self):
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="EMAIL")))
        assert _validate(config, {"personal": {"email": "   "}}) == {}


# ── Degrade + no-format fields + merge semantics (R7.3/R7.5) ──────────────────────────


class TestDegradeAndMerge:
    def test_field_without_a_format_is_ignored(self):
        config = _config(_field("first_name", "personal", fmt=None))
        assert _validate(config, {"personal": {"first_name": "whatever"}}) == {}

    def test_unknown_token_degrades_to_not_enforced(self):
        # A stray token that slipped past the reader's degrade (R7.3) is simply not enforced —
        # get_checker returns None, so the step skips it rather than crashing (R7.5).
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="NOPE")))
        assert _validate(config, {"personal": {"email": "anything"}}) == {}

    def test_format_errors_merge_alongside_preexisting_errors(self):
        # The step MERGES into the shared map — it never clobbers an error another pass recorded.
        config = _config(_field("email", "personal", fmt=FieldFormat(checker="EMAIL")))
        errors: dict[str, FieldError] = {
            "personal.last_name": FieldError(code=VALIDATION_REQUIRED, detail="is required")
        }
        WritesMixin._validate_field_formats(config, {"personal": {"email": "bad"}}, errors)
        assert set(errors) == {"personal.last_name", "personal.email"}

    def test_multiple_formatted_fields_each_contribute_their_error(self):
        config = _config(
            _field("email", "personal", fmt=FieldFormat(checker="EMAIL")),
            _field("iban", "personal", fmt=FieldFormat(checker="IBAN")),
        )
        record = {"personal": {"email": "bad", "iban": INVALID_IBAN}}
        errors = _validate(config, record)
        assert set(errors) == {"personal.email", "personal.iban"}
