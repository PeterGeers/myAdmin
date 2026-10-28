"""
Member Application Form (application-app) — task 3.1 tests.

Pins the FOUR public-application field attributes and the `FieldFormat` validator value
object added to the member field data model, mirroring the existing `member_number_format`
carry (design seam c / §5; D20):

  * `application_visible`   (bool)             — on the public application form? (R4.2/R4.3)
  * `application_required`  (bool)             — required ON THE FORM (overlay-only, R4b)
  * `application_choices`   (tuple[str,…]|None) — enum application SUBSET (R4a); None → full set
  * `format`                (FieldFormat|None)  — declarative field validator (R7.1); None → none

These are the RAW DATA carriers only (task 3.1): the reader (`_build_format` + the three attr
reads, task 3.3), the registry (`field_formats.py`, task 3.2), the enforcement step (task 3.4),
and the Flask authoring/projection (task 8.x) land in later tasks. This test therefore asserts
SHAPE + DEFAULTS + immutability, not behaviour.

The four shapes that carry the attributes (D20 — "on BOTH overlay fields and fixed-field
overrides", plus the base `FixedField` default and the resolved output `ResolvedField`):
`FixedField`, `OverlayField`, `FixedFieldOverride`, `ResolvedField`.

Task 3.6 (test consolidation/audit) adds one genuinely-missing assertion on this same
data model: that the PLATFORM ``required`` floor and the public-form ``application_required``
flag are two INDEPENDENT axes (``TestPlatformRequiredAndApplicationRequiredAreIndependentAxes``)
— the SAM-plane data-contract counterpart of the Flask "application-required cannot relax a
platform-required field" Save guard (R14.15 / R4c.3).

Validates: Requirements R4.2, R4a, R4b, R7.1, R14.15
"""

from __future__ import annotations

import dataclasses

import pytest

from sam.members.domain.field_resolver import (
    FieldFormat,
    FieldOrigin,
    FieldScope,
    FixedFieldOverride,
    OverlayField,
    ResolvedField,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    FieldFormat as FieldFormatFromFixed,
    FieldGroup,
    FieldType,
    FixedField,
)

#: The attribute names task 3.1 adds, and their "off the public form / back-compatible" default
#: on the three value-carrying shapes (the fixed base + the two overlay-authoring shapes +
#: the resolved output). `FixedFieldOverride` uses a tri-state `None` ("leave base as-is") for
#: the two booleans, matching every other override attribute.
_APPLICATION_ATTRS = ("application_visible", "application_required", "application_choices", "format")


class TestFieldFormatValueObject:
    """`FieldFormat{checker, params}` — the declarative validator value object (R7.1/D16)."""

    def test_field_format_is_re_exported_from_both_surfaces(self):
        # Defined in fixed_fields.py (beside MemberNumberFormat) and re-exported through the
        # public domain surface `field_resolver` — the SAME object, so every import path agrees.
        assert FieldFormat is FieldFormatFromFixed

    def test_carries_checker_and_params_with_empty_params_default(self):
        fmt = FieldFormat(checker="EMAIL")
        assert fmt.checker == "EMAIL"
        assert fmt.params == {}

    def test_params_are_carried_verbatim(self):
        fmt = FieldFormat(checker="IBAN", params={"country": "NL"})
        assert fmt.checker == "IBAN"
        assert fmt.params == {"country": "NL"}

    def test_is_frozen(self):
        fmt = FieldFormat(checker="EMAIL")
        with pytest.raises(dataclasses.FrozenInstanceError):
            fmt.checker = "IBAN"  # type: ignore[misc]


class TestApplicationAttributeDefaults:
    """Every shape carries the four attrs with back-compatible, form-off defaults."""

    def test_fixed_field_defaults(self):
        f = FixedField(key="first_name", group=FieldGroup.PERSONAL, type=FieldType.STRING)
        assert f.application_visible is False
        assert f.application_required is False
        assert f.application_choices is None
        assert f.format is None

    def test_overlay_field_defaults(self):
        f = OverlayField(key="motor_type", type=FieldType.STRING)
        assert f.application_visible is False
        assert f.application_required is False
        assert f.application_choices is None
        assert f.format is None

    def test_fixed_field_override_defaults_are_tri_state_none(self):
        # An override that touches none of these leaves base behaviour unchanged → all None
        # (the "leave base as-is" convention every override attribute uses), including the booleans.
        o = FixedFieldOverride()
        assert o.application_visible is None
        assert o.application_required is None
        assert o.application_choices is None
        assert o.format is None

    def test_resolved_field_defaults(self):
        rf = ResolvedField(
            key="first_name",
            group="personal",
            type=FieldType.STRING,
            required=False,
            origin=FieldOrigin.FIXED,
        )
        assert rf.application_visible is False
        assert rf.application_required is False
        assert rf.application_choices is None
        assert rf.format is None


class TestApplicationAttributesCarryValues:
    """The attributes accept and carry explicit values (the shape readers/validators consume)."""

    def test_overlay_field_carries_all_four(self):
        f = OverlayField(
            key="membership_level",
            type=FieldType.ENUM,
            choices=("gold", "silver", "bronze"),
            application_visible=True,
            application_required=True,
            application_choices=("silver", "bronze"),
            format=FieldFormat(checker="EMAIL"),
        )
        assert f.application_visible is True
        assert f.application_required is True
        assert f.application_choices == ("silver", "bronze")
        assert f.format == FieldFormat(checker="EMAIL")

    def test_fixed_override_puts_a_fixed_field_on_the_form(self):
        # D20: a fixed-field override is how a tenant opts a platform fixed field (e.g.
        # membership_type) onto the public form, with its own application subset.
        o = FixedFieldOverride(
            application_visible=True,
            application_required=True,
            application_choices=("student", "regular"),
        )
        assert o.application_visible is True
        assert o.application_required is True
        assert o.application_choices == ("student", "regular")

    def test_resolved_field_carries_the_resolved_values(self):
        rf = ResolvedField(
            key="email",
            group="personal",
            type=FieldType.STRING,
            required=True,
            origin=FieldOrigin.FIXED,
            application_visible=True,
            application_required=True,
            format=FieldFormat(checker="EMAIL"),
        )
        assert rf.application_visible is True
        assert rf.application_required is True
        assert rf.format == FieldFormat(checker="EMAIL")


class TestPlatformRequiredAndApplicationRequiredAreIndependentAxes:
    """R14.15 (SAM-plane data contract): ``required`` (the PLATFORM floor) and
    ``application_required`` (the public-form flag, R4b) are two SEPARATE axes on a
    resolved field — one never aliases or derives from the other.

    This is the data-model invariant the Flask Save-time ``application_required cannot
    relax a platform-required field`` guard (R4c.3 — covered on the author plane by
    ``backend/tests/unit/test_members_config_validation.py``) protects: the "cannot
    relax" rule is only meaningful because the two flags are independent and a field can
    be platform-required while application-OPTIONAL and vice-versa. The SAM reader
    carries both 1:1 (``TestOverlayApplicationAttributes``) and the submit validator
    (task 2.x / R14.15 enforcement) reads them as distinct inputs — so the model must
    keep them distinct. Pinned here so the two axes can never silently collapse into one.
    """

    def test_platform_required_field_can_be_application_optional(self):
        # The platform floor stays required=True while the field is NOT required on the
        # public form (application_required=False). The axes do not alias.
        rf = ResolvedField(
            key="last_name",
            group="personal",
            type=FieldType.STRING,
            required=True,              # platform-required (identity anchor)
            origin=FieldOrigin.FIXED,
            application_visible=True,
            application_required=False,  # but NOT required on the public form
        )
        assert rf.required is True
        assert rf.application_required is False

    def test_platform_optional_field_can_be_application_required(self):
        # The mirror: a platform-OPTIONAL field may be TIGHTENED to required on the form
        # (application_required=True) without touching the platform floor (required=False).
        rf = ResolvedField(
            key="phone",
            group="personal",
            type=FieldType.STRING,
            required=False,              # platform-optional
            origin=FieldOrigin.FIXED,
            application_visible=True,
            application_required=True,   # required on the public form
        )
        assert rf.required is False
        assert rf.application_required is True

    def test_application_required_defaults_off_regardless_of_platform_required(self):
        # application_required does NOT inherit the platform floor: a platform-required
        # field that authored no application flag is application_required=False by default
        # (off the public form until a tenant opts it on — R4.2/R4b back-compat).
        rf = ResolvedField(
            key="email",
            group="personal",
            type=FieldType.STRING,
            required=True,               # platform-required
            origin=FieldOrigin.FIXED,
        )
        assert rf.required is True
        assert rf.application_required is False  # not derived from `required`

    def test_required_and_application_required_are_distinct_dataclass_fields(self):
        # Belt-and-suspenders: they are two separately-named fields on the shape, so no
        # refactor can accidentally make one an alias/property of the other.
        names = {f.name for f in dataclasses.fields(ResolvedField)}
        assert {"required", "application_required"} <= names


class TestAllShapesExposeTheAttributes:
    """Lock-step: all four modelled shapes expose the four attributes (introspected, not hand-copied)."""

    @pytest.mark.parametrize("klass", [FixedField, OverlayField, FixedFieldOverride, ResolvedField])
    def test_shape_exposes_the_four_application_attributes(self, klass):
        names = {f.name for f in dataclasses.fields(klass)}
        missing = set(_APPLICATION_ATTRS) - names
        assert not missing, f"{klass.__name__} is missing application attrs: {sorted(missing)}"


class TestFieldScopeValuesAreDerivedFromOptions:
    """C5/F7: ``FieldScope.values`` is a DERIVED projection of the ONE canonical ``options``,
    never an independently stored second copy — so the observed ``FieldScope(values=())``
    divergence (bug manifestation #2) is impossible BY CONSTRUCTION.

    The scope axis has ONE vocabulary. ``FieldScope`` stores only ``options`` (rich
    :class:`EnumOption` entries); ``values`` is ``tuple(o.value for o in options)`` computed on
    read. There is a single stored list, so ``options`` and ``values`` can never disagree.
    Validates: Requirements 2.1, 2.6.
    """

    def test_values_projects_bare_strings_from_options(self):
        scope = FieldScope(
            enabled=True,
            options=(EnumOption(value="Noord"), EnumOption(value="Zuid")),
        )
        assert scope.values == ("Noord", "Zuid")
        assert tuple(scope.values) == tuple(o.value for o in scope.options)

    def test_empty_options_derives_empty_values(self):
        scope = FieldScope(enabled=True)
        assert scope.options == ()
        assert scope.values == ()

    def test_values_is_not_an_independent_settable_field(self):
        # The divergence was only possible because `values` was a stored sibling of `options`.
        # It is now a read-only derived property: not a dataclass field, and not assignable.
        names = {f.name for f in dataclasses.fields(FieldScope)}
        assert "options" in names
        assert "values" not in names  # derived, never stored
        scope = FieldScope(options=(EnumOption(value="x"),))
        with pytest.raises(AttributeError):
            scope.values = ("y",)  # type: ignore[misc]

    def test_values_always_tracks_options_cannot_diverge(self):
        # Whatever `options` is, `values` is exactly its value projection — there is no code path
        # that can populate `options` while leaving `values` empty (the FieldScope(values=()) bug).
        opts = (EnumOption(value="a"), EnumOption(value="b"), EnumOption(value="c"))
        scope = FieldScope(enabled=True, options=opts, required_for=("Members_CRUD",))
        assert list(scope.values) == [o.value for o in scope.options]
