"""
Member Application Form (application-app) — task 3.5 tests.

Pins the enum **application choice SUBSET** operations (R4a; design seam c): the public form
exposes ONLY the declared subset (R4a.2), a submitted value is validated against that subset
(R4a.3), and a subset entry that is not one of the field's resolved choices is a fail-loud
config error (R4a.4). The two pure authorities both operations run through:

  * `application_subset_choices(field)`  — the choices exposed on the public form
  * `validate_application_choice(field, value)` — validate a submitted value against the subset

Validates: Requirements R4a.2, R4a.3, R4a.4
"""

from __future__ import annotations

import pytest

from sam.members.domain.application_choices import (
    application_subset_choices,
    validate_application_choice,
)
from sam.members.domain.error_codes import VALIDATION_MUST_BE_ONE_OF
from sam.members.domain.field_resolver import (
    FieldOrigin,
    OverlayError,
    ResolvedField,
)
from sam.members.domain.fixed_fields import EnumOption, FieldType


def _enum_field(
    *,
    choices=("regular", "student", "honorary", "staff_only"),
    application_choices=None,
    field_type=FieldType.ENUM,
    options=None,
) -> ResolvedField:
    """A resolved ENUM field with a closed choice set, optionally carrying a subset."""
    return ResolvedField(
        key="membership_type",
        group="membership",
        type=field_type,
        required=False,
        origin=FieldOrigin.FIXED,
        choices=choices,
        options=options,
        application_visible=True,
        application_choices=application_choices,
    )


# ── R4a.2 — the public form exposes ONLY the declared subset, else the full set ───────


class TestSubsetExposure:
    def test_no_subset_declared_exposes_full_choice_set(self):
        # R4a.2 back-compatible default: None → the field's full resolved choices.
        field = _enum_field(application_choices=None)
        assert application_subset_choices(field) == (
            "regular",
            "student",
            "honorary",
            "staff_only",
        )

    def test_declared_subset_exposes_only_the_subset_in_declared_order(self):
        # R4a.2: a declared subset is the ONLY thing offered, preserving its declared order.
        field = _enum_field(application_choices=("student", "regular"))
        assert application_subset_choices(field) == ("student", "regular")

    def test_subset_hides_a_staff_only_choice(self):
        # The public-safe subset excludes the staff-facing entry.
        field = _enum_field(application_choices=("regular", "student"))
        exposed = application_subset_choices(field)
        assert "staff_only" not in exposed
        assert "honorary" not in exposed

    def test_subset_tolerates_rich_option_shaped_choices(self):
        # `choices` may carry rich {value,label} objects in some paths — subset ⊆ check must
        # compare against the coerced VALUE, never choke on the dict (would be a 502).
        options = (
            EnumOption(value="regular", label={"nl": "Regulier"}),
            EnumOption(value="student", label={"nl": "Student"}),
        )
        field = _enum_field(
            choices=("regular", "student"),
            options=options,
            application_choices=("student",),
        )
        assert application_subset_choices(field) == ("student",)


# ── R4a.4 — a subset entry not in the field's choices is a fail-loud config bug ───────


class TestSubsetFailLoud:
    def test_subset_entry_not_in_choices_raises_overlay_error(self):
        # R4a.4: a subset must be ⊆ the field choices; an off-list entry is a config bug.
        field = _enum_field(application_choices=("regular", "not_a_real_type"))
        with pytest.raises(OverlayError) as exc:
            application_subset_choices(field)
        assert "membership.membership_type" in exc.value.reasons

    def test_fail_loud_reason_names_the_offending_value(self):
        field = _enum_field(application_choices=("ghost",))
        with pytest.raises(OverlayError) as exc:
            application_subset_choices(field)
        assert "ghost" in exc.value.reasons["membership.membership_type"]

    def test_valid_subset_does_not_raise(self):
        field = _enum_field(application_choices=("regular", "honorary"))
        # Must not raise — a proper subset.
        assert application_subset_choices(field) == ("regular", "honorary")

    def test_submit_against_broken_subset_also_fails_loud(self):
        # Validation re-runs the ⊆ guard, so a submit against a broken subset is a config bug.
        field = _enum_field(application_choices=("bogus",))
        with pytest.raises(OverlayError):
            validate_application_choice(field, "regular")


# ── R4a.3 — a submitted value is validated against the subset, not the full set ───────


class TestSubmitValidation:
    def test_value_inside_subset_is_accepted(self):
        field = _enum_field(application_choices=("regular", "student"))
        assert validate_application_choice(field, "student") is None

    def test_non_subset_value_rejected_even_if_valid_staff_choice(self):
        # R4a.3: `staff_only` is a valid staff-facing choice but NOT in the subset → rejected.
        field = _enum_field(application_choices=("regular", "student"))
        err = validate_application_choice(field, "staff_only")
        assert err is not None
        assert err.code == VALIDATION_MUST_BE_ONE_OF
        assert err.params == {"allowed": ["regular", "student"]}

    def test_value_outside_full_set_rejected(self):
        field = _enum_field(application_choices=("regular", "student"))
        assert validate_application_choice(field, "nonexistent") is not None

    def test_no_subset_validates_against_full_set(self):
        # R4a.2 default: with no subset, the full choice set is the acceptance set.
        field = _enum_field(application_choices=None)
        assert validate_application_choice(field, "honorary") is None
        assert validate_application_choice(field, "staff_only") is None
        assert validate_application_choice(field, "nope") is not None

    def test_blank_or_absent_value_is_required_ness_concern_not_subset(self):
        # A blank/absent value is left to the required-ness rule — not "outside the subset".
        field = _enum_field(application_choices=("regular", "student"))
        assert validate_application_choice(field, None) is None
        assert validate_application_choice(field, "") is None
        assert validate_application_choice(field, "   ") is None

    def test_non_enum_field_is_not_subset_gated(self):
        field = ResolvedField(
            key="first_name",
            group="personal",
            type=FieldType.STRING,
            required=False,
            origin=FieldOrigin.FIXED,
        )
        assert validate_application_choice(field, "anything") is None

    def test_open_enum_with_no_choices_is_not_subset_gated(self):
        # An enum with no resolved choices (open, tenant config) has nothing to gate against.
        field = _enum_field(choices=None, application_choices=None)
        assert validate_application_choice(field, "anything") is None
