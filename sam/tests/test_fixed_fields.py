"""
S5 Task 1.1 — tests for the fixed base field registry (personal + membership).

Unit tests pin the registry's shape (canonical keys, groups, the closed status enum) and
its validation behaviour (required-ness, per-type rules, partial updates). A property test
asserts the round-trip invariant: any member built from the registry's own definitions
validates, and clearing a required field always fails.

Validates: Requirements R2.1
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sam.members.domain.fixed_fields import (
    FIXED_FIELDS,
    FIXED_FIELD_GROUPS,
    MEMBERSHIP_FIELDS,
    PERSONAL_FIELDS,
    FieldGroup,
    FieldType,
    FieldValidationError,
    FixedField,
    MembershipStatus,
    canonical_keys,
    field_by_key,
    validate_fixed_fields,
)


# A minimal, fully-valid member record (fixed fields only) used as a baseline.
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


# ── Registry shape ────────────────────────────────────────────────────────────────────


def test_registry_covers_personal_and_membership_fields():
    personal_keys = {f.key for f in PERSONAL_FIELDS}
    membership_keys = {f.key for f in MEMBERSHIP_FIELDS}
    assert personal_keys == {
        "first_name",
        "last_name",
        "name_infix",
        "initials",
        "birth_date",
        "gender",
        "email",
        "phone",
        "street",
        "postal_code",
        "city",
        "country",
    }
    assert membership_keys == {
        "member_number",
        "status",
        "membership_type",
        "joined_date",
        "created_at",
        "updated_at",
    }


def test_all_fixed_fields_are_personal_or_membership():
    assert all(f.group in (FieldGroup.PERSONAL, FieldGroup.MEMBERSHIP) for f in FIXED_FIELDS)
    assert FIXED_FIELD_GROUPS[FieldGroup.PERSONAL] == PERSONAL_FIELDS
    assert FIXED_FIELD_GROUPS[FieldGroup.MEMBERSHIP] == MEMBERSHIP_FIELDS


def test_canonical_keys_are_unique_and_dotted():
    keys = canonical_keys()
    assert len(keys) == len(set(keys)) == len(FIXED_FIELDS)
    assert "membership.status" in keys
    assert "personal.first_name" in keys


def test_field_by_key_round_trips_and_misses_gracefully():
    for f in FIXED_FIELDS:
        assert field_by_key(f.dotted_key()) is f
    assert field_by_key("personal.unknown") is None


def test_fixed_fields_are_immutable():
    with pytest.raises((AttributeError, TypeError)):
        FIXED_FIELDS[0].key = "mutated"  # type: ignore[misc]


def test_status_field_is_the_closed_membership_enum():
    status = field_by_key("membership.status")
    assert status is not None and status.type is FieldType.ENUM
    assert set(status.choices) == {s.value for s in MembershipStatus}


# ── Validation: happy path ────────────────────────────────────────────────────────────


def test_valid_member_passes():
    validate_fixed_fields(_valid_member())  # must not raise


def test_optional_fields_may_be_absent_or_null():
    m = _valid_member()
    del m["personal"]["street"]
    m["personal"]["birth_date"] = None
    m["personal"]["phone"] = None
    validate_fixed_fields(m)  # optional → fine


# ── Validation: required-ness ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "group,key",
    [
        ("personal", "first_name"),
        ("personal", "last_name"),
        # NOTE: email is NOT required (A.2b) — 66% of real members have none; see the
        # dedicated test_email_is_optional below. member_number is NOT required either (s5k) —
        # see test_member_number_is_optional below.
        ("membership", "status"),
        ("membership", "membership_type"),
        ("membership", "joined_date"),
    ],
)
def test_missing_required_field_fails(group, key):
    m = _valid_member()
    del m[group][key]
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert f"{group}.{key}" in exc.value.errors


def test_email_is_optional():
    # A.2b: email is NOT a required fixed field — a member record with no email is valid
    # (records-only members without a login account; the majority of a real membership).
    m = _valid_member()
    del m["personal"]["email"]
    validate_fixed_fields(m)  # must not raise


def test_member_number_is_optional():
    # s5k: member_number is a plain OPTIONAL string — sponsors / clubs / numberless members
    # are valid. No auto-generation and no uniqueness guard; an absent number is fine, and an
    # empty string is treated as absent (only a PRESENT value is format-checked elsewhere).
    m = _valid_member()
    del m["membership"]["member_number"]
    validate_fixed_fields(m)  # must not raise


def test_null_required_field_fails():
    m = _valid_member()
    m["membership"]["status"] = None
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert "membership.status" in exc.value.errors


@pytest.mark.parametrize("blank", ["", " ", "   "])
def test_blank_optional_string_is_valid_clearing_an_optional_field(blank):
    # Clearing an OPTIONAL string field (e.g. tussenvoegsel/name_infix) is a normal edit — a
    # blank/whitespace value means "empty", NOT a "must not be blank" error. (Regression: a
    # cleared tussenvoegsel wrongly returned 422 "must not be blank".)
    m = _valid_member()
    m["personal"]["name_infix"] = blank
    validate_fixed_fields(m)  # must not raise


@pytest.mark.parametrize("blank", ["", " ", "   "])
def test_blank_required_string_still_fails(blank):
    # A REQUIRED string field still rejects a blank/whitespace value.
    m = _valid_member()
    m["personal"]["first_name"] = blank
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    # v1.0: the error is a FieldError carrying a machine code + the English detail.
    fe = exc.value.errors["personal.first_name"]
    assert fe.code == "errors.validation.mustNotBeBlank"
    assert fe.detail == "must not be blank"


def test_partial_update_skips_absent_required_fields_but_still_checks_present_ones():
    # Absent key in a partial update = "leave unchanged" → allowed.
    validate_fixed_fields({"membership": {"status": "active"}}, partial=True)
    # But a present, invalid value is still rejected even in partial mode.
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields({"membership": {"status": "bogus"}}, partial=True)
    assert "membership.status" in exc.value.errors


# ── Validation: per-type rules ────────────────────────────────────────────────────────


def test_invalid_status_enum_fails():
    m = _valid_member()
    m["membership"]["status"] = "vip"
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert "membership.status" in exc.value.errors


@pytest.mark.parametrize("bad_date", ["2020-13-01", "01-01-2020", "2020/01/01", "not-a-date", ""])
def test_invalid_date_fails(bad_date):
    m = _valid_member()
    m["membership"]["joined_date"] = bad_date
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert "membership.joined_date" in exc.value.errors


def test_blank_required_string_fails():
    m = _valid_member()
    m["personal"]["first_name"] = "   "
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert "personal.first_name" in exc.value.errors


def test_wrong_type_string_fails():
    m = _valid_member()
    m["personal"]["first_name"] = 12345
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    assert "personal.first_name" in exc.value.errors


def test_all_errors_are_collected_at_once():
    m = {"personal": {}, "membership": {}}
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(m)
    required = {f.dotted_key() for f in FIXED_FIELDS if f.required}
    assert set(exc.value.errors) == required


# ── Property-based test ───────────────────────────────────────────────────────────────


def _value_for(fld: FixedField) -> st.SearchStrategy:
    """A generator that produces a valid value for a given fixed field."""
    if fld.type is FieldType.ENUM:
        # A closed enum draws from its choices; an OPEN enum (choices=None, e.g. gender —
        # tenant config, R4.2) accepts any non-blank string.
        if fld.choices is None:
            return st.text(min_size=1).filter(lambda s: s.strip() != "")
        return st.sampled_from(list(fld.choices))
    if fld.type is FieldType.DATE:
        return st.dates().map(lambda d: d.isoformat())
    # STRING / REFERENCE: any non-blank text.
    return st.text(min_size=1).filter(lambda s: s.strip() != "")


@st.composite
def _valid_members(draw) -> dict:
    """Build a member whose fixed fields are all populated from the registry definitions."""
    record: dict[str, dict] = {"personal": {}, "membership": {}}
    for fld in FIXED_FIELDS:
        record[fld.group.value][fld.key] = draw(_value_for(fld))
    return record


@given(_valid_members())
def test_property_registry_generated_members_always_validate(member):
    # Any record built purely from the registry's own field definitions must validate.
    validate_fixed_fields(member)


@given(_valid_members(), st.sampled_from([f for f in FIXED_FIELDS if f.required]))
def test_property_clearing_any_required_field_always_fails(member, required_field):
    member[required_field.group.value].pop(required_field.key, None)
    with pytest.raises(FieldValidationError) as exc:
        validate_fixed_fields(member)
    assert required_field.dotted_key() in exc.value.errors
