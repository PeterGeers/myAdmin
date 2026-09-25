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
    FieldError,
    MEMBER_NUMBER_FORMAT,
    VALIDATION_INVALID_DATE,
    VALIDATION_MUST_BE_A_STRING,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_MUST_NOT_BE_BLANK,
    VALIDATION_REQUIRED,
)
from sam.members.domain.fixed_fields import (
    FieldValidationError,
    MembershipStatus,
    validate_fixed_fields,
)


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
            "status": MembershipStatus.ACTIVE.value,
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
    del m["personal"]["first_name"]
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    fe = exc.value.errors["personal.first_name"]
    assert fe.code == VALIDATION_REQUIRED
    # English detail preserved (the pre-v1.0 message).
    assert fe.detail == "is required"


@pytest.mark.parametrize("blank", ["", " ", "   "])
def test_blank_required_string_carries_must_not_be_blank_code(blank):
    m = _valid_member()
    m["personal"]["first_name"] = blank
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    fe = exc.value.errors["personal.first_name"]
    assert fe.code == VALIDATION_MUST_NOT_BE_BLANK
    assert fe.detail == "must not be blank"


def test_wrong_type_string_carries_must_be_a_string_code():
    m = _valid_member()
    m["personal"]["first_name"] = 12345
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert exc.value.errors["personal.first_name"].code == VALIDATION_MUST_BE_A_STRING


def test_invalid_status_enum_carries_must_be_one_of_code_with_allowed_params():
    m = _valid_member()
    m["membership"]["status"] = "vip"
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    fe = exc.value.errors["membership.status"]
    assert fe.code == VALIDATION_MUST_BE_ONE_OF
    # params.allowed carries the machine list for interpolation; detail keeps the English join.
    assert fe.params is not None and "allowed" in fe.params
    assert MembershipStatus.ACTIVE.value in fe.params["allowed"]
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
