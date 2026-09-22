"""
S5c Task 1.5 — unit tests for the **calculated (derived) field** derivations (design C-FIELDS, R4.4).

A calculated field is derived, read-only, and NEVER stored — it is a pure function of the stored
fixed fields. These tests pin each derivation named in the design "Field classification table"
(design Data Models):

    display_name      ← first_name [+ name_infix] + last_name
    age               ← birth_date
    birthday          ← birth_date (MM-DD, year-independent)
    years_member      ← joined_date
    application_year  ← created_at (record creation year)

The contract every derivation shares (R4.4): a missing/blank input yields ``None`` (the field is
simply not shown) and NEVER raises. Edge cases covered: absent groups, blank/None inputs,
malformed dates, future dates (age/tenure can't be negative), leap-year birthday.

Validates: Requirements 4.4, 4.6, 4.7
"""

from __future__ import annotations

import datetime as _dt

import pytest

from sam.members.domain.calculated_fields import (
    CALCULATED_FIELDS,
    CalculatedField,
    calculated_field_by_key,
    compute_calculated_fields,
)
from sam.members.domain.calculated_fields import (
    _derive_age,
    _derive_application_year,
    _derive_birthday,
    _derive_display_name,
    _derive_years_member,
)


# A fixed reference "today" so age/years_member are deterministic regardless of the run date.
_TODAY = _dt.date(2025, 6, 15)


def _record(**groups) -> dict:
    """A member record with the given ``personal`` / ``membership`` sub-mappings."""
    rec: dict = {}
    if "personal" in groups:
        rec["personal"] = groups["personal"]
    if "membership" in groups:
        rec["membership"] = groups["membership"]
    return rec


# ── Registry shape ─────────────────────────────────────────────────────────────────────


def test_calculated_registry_covers_the_five_derived_fields():
    keys = {c.key for c in CALCULATED_FIELDS}
    assert keys == {"display_name", "age", "birthday", "years_member", "application_year"}


def test_every_calculated_field_declares_inputs_and_is_computable():
    for c in CALCULATED_FIELDS:
        assert isinstance(c, CalculatedField)
        assert c.inputs, f"{c.key} must declare its inputs for traceability"
        assert c.compute is not None, f"{c.key} must have a derivation"


def test_calculated_field_by_key_round_trips_and_misses_gracefully():
    for c in CALCULATED_FIELDS:
        assert calculated_field_by_key(c.dotted_key()) is c
    assert calculated_field_by_key("personal.nope") is None


# ── display_name ─────────────────────────────────────────────────────────────────────


def test_display_name_joins_first_infix_last():
    rec = _record(personal={"first_name": "Jan", "name_infix": "de", "last_name": "Vries"})
    assert _derive_display_name(rec) == "Jan de Vries"


def test_display_name_omits_blank_infix():
    rec = _record(personal={"first_name": "Jan", "name_infix": "", "last_name": "Jansen"})
    assert _derive_display_name(rec) == "Jan Jansen"


def test_display_name_without_infix_key():
    rec = _record(personal={"first_name": "Anna", "last_name": "Bakker"})
    assert _derive_display_name(rec) == "Anna Bakker"


def test_display_name_only_first_name():
    assert _derive_display_name(_record(personal={"first_name": "Sam"})) == "Sam"


@pytest.mark.parametrize(
    "personal",
    [
        {},                                   # empty personal group
        {"first_name": "", "last_name": ""},  # all blank
        {"first_name": "   "},                # whitespace only
    ],
)
def test_display_name_missing_or_blank_inputs_return_none(personal):
    assert _derive_display_name(_record(personal=personal)) is None


def test_display_name_missing_group_returns_none():
    assert _derive_display_name({}) is None


# ── age ────────────────────────────────────────────────────────────────────────────────


def test_age_before_birthday_this_year():
    # Born 1980-12-31; on 2025-06-15 the birthday has not occurred yet this year → 44.
    rec = _record(personal={"birth_date": "1980-12-31"})
    assert _derive_age(rec, today=_TODAY) == 44


def test_age_after_birthday_this_year():
    # Born 1980-01-01; birthday already passed → 45.
    rec = _record(personal={"birth_date": "1980-01-01"})
    assert _derive_age(rec, today=_TODAY) == 45


def test_age_on_exact_birthday():
    rec = _record(personal={"birth_date": "2000-06-15"})
    assert _derive_age(rec, today=_TODAY) == 25


def test_age_future_birth_date_is_none_never_negative():
    rec = _record(personal={"birth_date": "2030-01-01"})
    assert _derive_age(rec, today=_TODAY) is None


@pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date", "2020-13-40", {}])
def test_age_missing_or_malformed_returns_none(bad):
    rec = _record(personal={} if bad == {} else {"birth_date": bad})
    assert _derive_age(rec, today=_TODAY) is None


def test_age_missing_group_returns_none():
    assert _derive_age({}, today=_TODAY) is None


def test_age_accepts_datetime_prefixed_string():
    rec = _record(personal={"birth_date": "1990-06-15T10:00:00"})
    assert _derive_age(rec, today=_TODAY) == 35


# ── birthday (MM-DD) ─────────────────────────────────────────────────────────────────


def test_birthday_formats_month_day():
    rec = _record(personal={"birth_date": "1980-05-04"})
    assert _derive_birthday(rec) == "05-04"


def test_birthday_leap_day():
    rec = _record(personal={"birth_date": "2000-02-29"})
    assert _derive_birthday(rec) == "02-29"


def test_birthday_single_digit_zero_padded():
    rec = _record(personal={"birth_date": "1999-01-09"})
    assert _derive_birthday(rec) == "01-09"


@pytest.mark.parametrize("bad", [None, "", "garbage", "2020-02-30"])
def test_birthday_missing_or_malformed_returns_none(bad):
    assert _derive_birthday(_record(personal={"birth_date": bad})) is None


def test_birthday_missing_group_returns_none():
    assert _derive_birthday({}) is None


# ── years_member ──────────────────────────────────────────────────────────────────────


def test_years_member_before_anniversary_this_year():
    # Joined 2020-12-01; anniversary not reached on 2025-06-15 → 4.
    rec = _record(membership={"joined_date": "2020-12-01"})
    assert _derive_years_member(rec, today=_TODAY) == 4


def test_years_member_after_anniversary_this_year():
    rec = _record(membership={"joined_date": "2020-01-01"})
    assert _derive_years_member(rec, today=_TODAY) == 5


def test_years_member_same_year_join_is_zero():
    rec = _record(membership={"joined_date": "2025-01-01"})
    assert _derive_years_member(rec, today=_TODAY) == 0


def test_years_member_future_join_date_is_none():
    rec = _record(membership={"joined_date": "2030-01-01"})
    assert _derive_years_member(rec, today=_TODAY) is None


@pytest.mark.parametrize("bad", [None, "", "   ", "nope"])
def test_years_member_missing_or_malformed_returns_none(bad):
    assert _derive_years_member(_record(membership={"joined_date": bad}), today=_TODAY) is None


def test_years_member_missing_group_returns_none():
    assert _derive_years_member({}, today=_TODAY) is None


# ── application_year ─────────────────────────────────────────────────────────────────


def test_application_year_from_created_at():
    rec = _record(membership={"created_at": "2021-09-30"})
    assert _derive_application_year(rec) == 2021


def test_application_year_from_iso_timestamp():
    rec = _record(membership={"created_at": "2019-03-01T12:34:56"})
    assert _derive_application_year(rec) == 2019


@pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date"])
def test_application_year_missing_or_malformed_returns_none(bad):
    assert _derive_application_year(_record(membership={"created_at": bad})) is None


def test_application_year_missing_group_returns_none():
    assert _derive_application_year({}) is None


def test_application_year_falls_back_to_joined_date_year_when_no_created_at():
    """When created_at is absent, application_year derives from the joined_date year (1a)."""
    rec = _record(membership={"joined_date": "1979-08-07"})
    assert _derive_application_year(rec) == 1979


def test_application_year_prefers_created_at_over_joined_date():
    """created_at wins when both are present (joined_date is only the fallback)."""
    rec = _record(membership={"created_at": "2021-01-02", "joined_date": "1979-08-07"})
    assert _derive_application_year(rec) == 2021


# ── evaluate() + compute_calculated_fields() (the presentation-layer entry points) ─────


def test_evaluate_delegates_to_the_derivation():
    display = calculated_field_by_key("personal.display_name")
    rec = _record(personal={"first_name": "Kim", "last_name": "Smit"})
    assert display.evaluate(rec) == "Kim Smit"


def test_compute_calculated_fields_returns_every_key_and_never_raises():
    rec = _record(
        personal={"first_name": "Jan", "name_infix": "van", "last_name": "Dijk", "birth_date": "1990-06-15"},
        membership={"joined_date": "2015-01-01", "created_at": "2015-01-02"},
    )
    result = compute_calculated_fields(rec)
    # Every calculated dotted key is present in the projection.
    assert set(result) == {c.dotted_key() for c in CALCULATED_FIELDS}
    assert result["personal.display_name"] == "Jan van Dijk"
    assert result["personal.birthday"] == "06-15"
    assert result["membership.application_year"] == 2015
    # age / years_member are computed against the real "today"; just assert they resolved to ints.
    assert isinstance(result["personal.age"], int)
    assert isinstance(result["membership.years_member"], int)


def test_compute_calculated_fields_all_none_on_empty_record():
    result = compute_calculated_fields({})
    assert set(result) == {c.dotted_key() for c in CALCULATED_FIELDS}
    assert all(v is None for v in result.values())


def test_compute_calculated_fields_tolerates_non_mapping_record():
    # Defensive: a non-mapping record never raises; every field is None.
    result = compute_calculated_fields(None)  # type: ignore[arg-type]
    assert all(v is None for v in result.values())
