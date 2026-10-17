"""S5 — API response & error standard v1.0, task 3.2/3.3: per-field error CODES.

Test-first (task 3.2): pins the NEW per-field shape for the whole Members domain-validation
surface. Before v1.0 the validators put a bare English string in the ``errors`` map; the
standard replaces each with a :class:`FieldError` (``code`` + ``params`` + ``detail``) so the
frontend can localize via the ``code`` and fall back to ``detail`` (RFC 9457 per-entry).

The behavioural OUTCOMES are unchanged (the same fields fail for the same inputs) — these tests
assert on ``.code`` (and ``.params`` where interpolated) instead of the old string, and confirm
the English ``detail`` is preserved so nothing is lost. The pre-existing behavioural tests in
``test_fixed_fields.py`` / ``test_members_scope_dimension_choices.py`` /
``test_membership_lifecycle.py`` keep their PASS/FAIL outcomes; only their value assertions move
to ``.code`` (updated in task 3.3).

Validates: Requirements R4 (error codes + i18n).
"""

from __future__ import annotations

import pytest

from sam.members.domain.error_codes import (
    MEMBER_NUMBER_FORMAT,
    VALIDATION_INVALID_DATE,
    VALIDATION_MUST_BE_A_STRING,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_MUST_NOT_BE_BLANK,
    VALIDATION_REQUIRED,
    FieldError,
)
from sam.members.domain.fixed_fields import (
    FieldGroup,
    FieldType,
    FieldValidationError,
    FixedField,
    _validate_value,
    validate_fixed_fields,
)

# retire-members-status-lifecycle-engine (§C): the closed `MembershipStatus` enum was deleted;
# `membership.status` is now a plain OPEN enum. A member's status is authored as a plain string
# ("active" is the platform create-time-ish default value) and ANY non-blank string validates.
_STATUS_ACTIVE = "active"


def _valid_member() -> dict:
    return {
        "personal": {
            "first_name": "Jan",
            "last_name": "Jansen",
            "name_infix": "de",
            "initials": "J.J.",
            "birth_date": "1980-05-04",
            "gender": "M",
            "email": "jan@example.org",
            "phone": "+31 6 12345678",
            "street": "Straat 1",
            "postal_code": "1011 AB",
            "city": "Amsterdam",
            "country": "NL",
        },
        "membership": {
            "member_number": "H-0001",
            "status": _STATUS_ACTIVE,
            "membership_type": "erelid",
            "joined_date": "2020-01-01",
        },
    }


# ── fixed_fields.validate_fixed_fields emits FieldError values (not bare strings) ──────


def test_error_map_values_are_field_errors_not_strings():
    # Every value in the errors map is a FieldError with a code + a non-empty English detail.
    m = {"personal": {}, "membership": {}}
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert exc.value.errors  # some required fields failed
    for key, fe in exc.value.errors.items():
        assert isinstance(fe, FieldError), f"{key} -> {fe!r} is not a FieldError"
        assert fe.code
        assert isinstance(fe.detail, str) and fe.detail.strip()


def test_required_field_carries_validation_required_code():
    m = _valid_member()
    # last_name is the still-required identity anchor (first_name is now optional).
    del m["personal"]["last_name"]
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    fe = exc.value.errors["personal.last_name"]
    assert fe.code == VALIDATION_REQUIRED
    # English detail preserved (the pre-v1.0 message).
    assert fe.detail == "is required"


@pytest.mark.parametrize("blank", ["", " ", "   "])
def test_blank_required_string_carries_must_not_be_blank_code(blank):
    m = _valid_member()
    m["personal"]["last_name"] = blank
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    fe = exc.value.errors["personal.last_name"]
    assert fe.code == VALIDATION_MUST_NOT_BE_BLANK
    assert fe.detail == "must not be blank"


def test_wrong_type_string_carries_must_be_a_string_code():
    m = _valid_member()
    m["personal"]["last_name"] = 12345
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert exc.value.errors["personal.last_name"].code == VALIDATION_MUST_BE_A_STRING


def test_status_open_enum_accepts_any_non_blank_value():
    # retire-members-status-lifecycle-engine (§C): `membership.status` is now an OPEN enum
    # (`choices=None`, like `gender`). A tenant-authored value the old closed set rejected
    # (e.g. "vip") now VALIDATES — the closed-set "must be one of" gate on status is GONE.
    # (Resolved tenant choices enforce membership downstream; the base only requires a
    # non-blank string.) This aligns with the task-1 exploration test's intended behavior.
    m = _valid_member()
    m["membership"]["status"] = "vip"
    validate_fixed_fields(m)  # must NOT raise


@pytest.mark.parametrize("blank", ["", "   "])
def test_status_open_enum_still_rejects_a_blank_value(blank):
    # Open enum still requires a NON-BLANK string (status is a required field), carrying the
    # must-be-a-string code — the open-enum path, not the deleted closed-set gate.
    m = _valid_member()
    m["membership"]["status"] = blank
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert exc.value.errors["membership.status"].code == VALIDATION_MUST_BE_A_STRING


def test_closed_enum_value_carries_must_be_one_of_code_with_allowed_params():
    # The `errors.validation.mustBeOneOf` code + its `allowed` params are STILL emitted for a
    # genuinely CLOSED enum field (a value outside `choices`). After the retirement no FIXED
    # field is closed, so this is pinned directly on the validator with a closed-choice field —
    # exactly the path a tenant OVERLAY enum with a declared `choices` list still takes
    # (the non-status enum-membership invariant preserved, design §3.5).
    closed = FixedField(
        key="club_section",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.ENUM,
        choices=("noord", "zuid"),
        label={"en": "Section", "nl": "Afdeling"},
    )
    fe = _validate_value(closed, "west")
    assert fe is not None
    assert fe.code == VALIDATION_MUST_BE_ONE_OF
    # params.allowed carries the machine list for interpolation; detail keeps the English join.
    assert fe.params is not None and "allowed" in fe.params
    assert fe.params["allowed"] == ["noord", "zuid"]
    assert "must be one of" in fe.detail


@pytest.mark.parametrize("bad_date", ["2020-13-01", "01-01-2020", "2020/01/01", "not-a-date"])
def test_invalid_date_carries_invalid_date_code(bad_date):
    m = _valid_member()
    m["membership"]["joined_date"] = bad_date
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert exc.value.errors["membership.joined_date"].code == VALIDATION_INVALID_DATE


def test_field_error_as_entry_shapes_rfc9457_dict():
    fe = FieldError(
        code=VALIDATION_MUST_BE_ONE_OF,
        detail="must be one of: active, inactive",
        params={"allowed": ["active", "inactive"]},
    )
    entry = fe.as_entry(field_key="membership.status")
    assert entry == {
        "field": "membership.status",
        "code": VALIDATION_MUST_BE_ONE_OF,
        "detail": "must be one of: active, inactive",
        "params": {"allowed": ["active", "inactive"]},
    }
    # A parameter-free reason entry omits both `field` and `params`.
    bare = FieldError(code=VALIDATION_REQUIRED, detail="is required").as_entry()
    assert bare == {"code": VALIDATION_REQUIRED, "detail": "is required"}


def test_member_number_format_code_constant_is_stable():
    # Guards the constant used by _validate_member_number / member-number checks (task 3.3).
    assert MEMBER_NUMBER_FORMAT == "errors.member.numberFormat"
