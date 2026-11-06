"""
SAM property test — spec 15 (sam-page-look-and-feel), task 5.2.

**Property 6: Invalid value is rejected and stored values are preserved.**

Feature: sam-page-look-and-feel, Property 6: For any supported attribute supplied a value outside
its permitted set, the Layer-1 authoring operation SHALL reject the setting, leave the Page's
previously stored Look_And_Feel_Settings values unchanged, and identify the rejected setting.

The operation under test is
:meth:`sam.members.domain.look_and_feel_settings_service.LookAndFeelSettingsService.set_setting`
(task 5.1) — the Layer-1 authoring authority for a Page's ``Look_And_Feel_Settings`` VALUES. It
validates the value against the attribute's permitted set (Req 4.5) BEFORE any write; an
out-of-set value raises :class:`LookAndFeelValidationError` and issues NO Change-Op, so the
Page's previously stored values are left UNCHANGED by construction.

This property pins that contract observably. For EACH of the seven supported attributes we
generate, via Hypothesis (>=100 iterations), values OUTSIDE that attribute's permitted set, seed
an arbitrary pre-existing resolved slice of stored values, attempt the set, and assert that:

1. the set is REJECTED with :class:`LookAndFeelValidationError`,
2. the writer records NO op (nothing reached storage),
3. a subsequent resolved read returns EXACTLY the previously stored values (unchanged), and
4. the error IDENTIFIES the rejected attribute (the client's own key, caller-safe to surface).

In-memory fakes (``FakeReader`` / ``RecordingWriter``) are reused from the task-5.1 unit suite
``test_look_and_feel_settings_service.py`` so this property runs on the exact same no-boto3 model
the service is unit-tested against (steering 34/35/39). Because task 5.3 edits the shared service
and may touch that unit file in parallel, this property lives in its OWN file (test-only task).

Hypothesis, >=100 iterations (steering 34).

Validates: Requirements 4.5
Properties: 6
"""

import os
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.look_and_feel_settings_service import (  # noqa: E402
    APPLICATION_FORM_PAGE_ID,
    LookAndFeelSettingsService,
    LookAndFeelValidationError,
    _COLOUR_ATTRIBUTES,
    _FONT_ATTRIBUTES,
    _FONT_NAME_PATTERN,
    _HEX_COLOUR_PATTERN,
    _PERMITTED_VALUES,
)
from sam.shared.page_styles import SUPPORTED_ATTRIBUTES  # noqa: E402

# Reuse the exact in-memory fakes the task-5.1 service unit suite uses, so this property runs on
# the same no-boto3 reader/writer model the service is tested against.
from sam.tests.test_look_and_feel_settings_service import (  # noqa: E402
    FakeReader,
    RecordingWriter,
)

_TENANT = "h-dcn"

# ─── A VALID stored slice (what must survive a rejected set, unchanged) ──────────────────
# Any subset of the supported attributes, each with a VALID value — this is the Page's
# previously-stored Look_And_Feel_Settings the rejected set must not perturb.
_VALID_BY_ATTR = {
    "color_primary": st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True),
    "color_accent": st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True),
    "font_heading": st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans"]),
    "font_body": st.sampled_from(["system", "Inter", "Lora", "Roboto", "Open Sans"]),
    "base_spacing": st.sampled_from(sorted(_PERMITTED_VALUES["base_spacing"])),
    "border_radius_global": st.sampled_from(
        sorted(_PERMITTED_VALUES["border_radius_global"])
    ),
    "shadow_style": st.sampled_from(sorted(_PERMITTED_VALUES["shadow_style"])),
}
assert set(_VALID_BY_ATTR) == set(SUPPORTED_ATTRIBUTES)


@st.composite
def _stored_slice(draw):
    """Draw an arbitrary (possibly empty) slice of VALID previously-stored values."""
    values = {}
    for attr, strat in _VALID_BY_ATTR.items():
        if draw(st.booleans()):
            values[attr] = draw(strat)
    return values


# ─── Generators for values OUTSIDE each attribute's permitted set (Req 4.5) ──────────────


def _enum_invalid(attribute):
    """Values outside a closed enum attribute's permitted set.

    Any value — string or otherwise — that is not one of the permitted enum members is rejected.
    """
    permitted = _PERMITTED_VALUES[attribute]
    # Only HASHABLE candidates: the service's enum check is ``value not in permitted`` against a
    # frozenset, which is only defined for hashable values (an unhashable value is not a realistic
    # authoring input and would raise before validation). None is excluded per-attribute below.
    return st.one_of(
        st.text().filter(lambda v: v not in permitted),
        st.integers(),
        st.booleans(),
        st.none(),  # NOTE: None is the CLEAR sentinel; excluded per-attribute below.
    )


# Colour attributes: a value must match ^#(RGB|RRGGBB)$. Anything else is invalid.
_colour_invalid = st.one_of(
    st.text(),  # arbitrary text (filtered against the real pattern below)
    st.integers(),
    st.booleans(),
    st.lists(st.text()),
    st.just("#12"),  # too short
    st.just("#12345"),  # 5 hex digits
    st.just("#1234567"),  # 7 hex digits
    st.just("2D5F8A"),  # missing leading '#'
    st.just("#GGGGGG"),  # non-hex characters
    st.just("rgb(0,0,0)"),
)

# Font attributes: a value must match ^[A-Za-z0-9][A-Za-z0-9 \-]{0,63}$. Anything else is invalid.
_font_invalid = st.one_of(
    st.text(),  # arbitrary text (filtered against the real pattern below)
    st.integers(),
    st.booleans(),
    st.lists(st.text()),
    st.just(""),  # blank
    st.just(" Inter"),  # leading space (first char must be alnum)
    st.just("bad{font}"),  # braces — a CSS-injection shape
    st.just("url(evil)"),  # parentheses
    st.just('Inter"; }'),  # quote + brace
    st.just("a" * 65),  # too long (max 64 chars)
)


def _invalid_value_strategy(attribute):
    """A strategy producing values OUTSIDE ``attribute``'s permitted set (never the clear sentinel).

    ``None`` is the service's explicit CLEAR sentinel (REMOVE), not a value rejection, so it is
    excluded here — this property is about VALUE rejection leaving stored values unchanged.
    """
    if attribute in _PERMITTED_VALUES:
        base = _enum_invalid(attribute)
    elif attribute in _COLOUR_ATTRIBUTES:
        base = _colour_invalid
    elif attribute in _FONT_ATTRIBUTES:
        base = _font_invalid
    else:  # pragma: no cover - the three branches above cover all seven supported attributes
        raise AssertionError(f"no invalid-value strategy for {attribute!r}")
    return base.filter(lambda v: v is not None)


def _is_actually_invalid(attribute, value):
    """True iff ``value`` is genuinely outside ``attribute``'s permitted set.

    Mirrors the service's own permitted-set checks so a generated value that happens to be VALID
    (e.g. an enum member, a well-formed hex colour, a safe font token) is assumed away rather than
    wrongly asserted as rejected.
    """
    if attribute in _PERMITTED_VALUES:
        return value not in _PERMITTED_VALUES[attribute]
    if attribute in _COLOUR_ATTRIBUTES:
        return not (isinstance(value, str) and _HEX_COLOUR_PATTERN.match(value))
    if attribute in _FONT_ATTRIBUTES:
        return not (isinstance(value, str) and _FONT_NAME_PATTERN.match(value))
    raise AssertionError(f"unknown attribute {attribute!r}")


# ─── Property ──────────────────────────────────────────────────────────────────────────


# Tag (exact, single-line):
# Feature: sam-page-look-and-feel, Property 6: For any supported attribute supplied a value outside its permitted set, the Layer-1 authoring operation SHALL reject the setting, leave the Page's previously stored Look_And_Feel_Settings values unchanged, and identify the rejected setting.
@settings(max_examples=200)
@given(
    data=st.data(),
    attribute=st.sampled_from(sorted(SUPPORTED_ATTRIBUTES)),
    stored=_stored_slice(),
)
def test_invalid_value_is_rejected_and_stored_values_preserved(data, attribute, stored):
    """Property 6: an out-of-set value is rejected, stored values survive, and the attr is named.

    Feature: sam-page-look-and-feel, Property 6: For any supported attribute supplied a value
    outside its permitted set, the Layer-1 authoring operation SHALL reject the setting, leave the
    Page's previously stored Look_And_Feel_Settings values unchanged, and identify the rejected
    setting.
    """
    bad_value = data.draw(_invalid_value_strategy(attribute))
    # Keep only genuinely out-of-set values (a generated value can coincidentally be valid).
    assume(_is_actually_invalid(attribute, bad_value))

    # The Page's previously-stored resolved view (what must remain UNCHANGED).
    reader = FakeReader({_TENANT: dict(stored)})
    writer = RecordingWriter()
    svc = LookAndFeelSettingsService(reader, writer)

    # 1) The set is REJECTED.
    try:
        svc.set_setting(_TENANT, APPLICATION_FORM_PAGE_ID, attribute, bad_value)
    except LookAndFeelValidationError as exc:
        # 4) The error IDENTIFIES the rejected attribute (caller-safe — the client's own key).
        assert attribute in str(exc), (
            f"error must name the rejected attribute {attribute!r}: got {exc!s}"
        )
    else:
        raise AssertionError(
            f"invalid value {bad_value!r} for {attribute!r} was NOT rejected"
        )

    # 2) The writer recorded NO op — nothing reached storage.
    assert writer.calls == [], "a rejected value must never reach the writer"

    # 3) A subsequent resolved read returns EXACTLY the previously stored values, unchanged.
    assert svc.get_settings(_TENANT, APPLICATION_FORM_PAGE_ID) == stored
