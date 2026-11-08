"""
SAM property test — spec 15 (sam-page-look-and-feel), task 1.3.

**Property 2: Layer-2 output depends only on the supplied values (page-type-agnostic).**

Feature: sam-page-look-and-feel, Property 2: For any two Pages supplied identical
Look_And_Feel_Settings values, render_page_styles SHALL produce identical styling output
regardless of Page type or any other Page state.

The Layer-2 generator (:func:`sam.shared.page_styles.render_page_styles`) takes ONLY a
settings VALUES mapping and holds no page-specific state — there is no page-type argument
and no other Page state it can read. This property pins that design contract observably:
two independently-constructed callers (modelling two different Pages — e.g. the application
form today and a future landing page — each carrying its OWN unrelated page state) that
supply the SAME Look_And_Feel_Settings values get byte-for-byte identical styling output.
"Page type / any other Page state" is modelled as arbitrary surrounding context that the
function never receives, so it cannot influence the output.

Hypothesis, >=100 iterations (steering 34).

Validates: Requirements 1.5, 4.3, 6.1, 6.2, 6.3
Properties: 2
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import render_page_styles  # noqa: E402

# ─── Generators for valid Look_And_Feel_Settings values ────────────────────────────────
# Each attribute draws from its permitted/valid value space; every attribute is optional so
# the generated mapping is any subset of the seven supported attributes (absent -> default,
# still page-type-agnostic). Values are the ones the Layer-2 lookup maps recognise, plus
# arbitrary hex-ish colour/font strings to exercise the free-form attributes.

_hex_color = st.from_regex(r"\#[0-9A-Fa-f]{6}", fullmatch=True)
_font_name = st.sampled_from(
    ["system", "Inter", "Lora", "Roboto", "Open Sans", "Merriweather", "Poppins"]
)
_base_spacing = st.sampled_from(["compact", "normal", "relaxed"])
_border_radius = st.sampled_from(["sharp", "rounded", "pill"])
_shadow_style = st.sampled_from(["none", "subtle", "medium", "dramatic"])


@st.composite
def _settings_values(draw):
    """Draw a valid (possibly partial) Look_And_Feel_Settings values mapping."""
    candidate = {
        "color_primary": draw(_hex_color),
        "color_accent": draw(_hex_color),
        "font_heading": draw(_font_name),
        "font_body": draw(_font_name),
        "base_spacing": draw(_base_spacing),
        "border_radius_global": draw(_border_radius),
        "shadow_style": draw(_shadow_style),
    }
    # Each attribute is independently present/absent so any subset is exercised: an absent
    # attribute falls back to the SAM-owned default, which is still page-agnostic.
    include = {
        key: draw(st.booleans()) for key in candidate
    }
    return {key: value for key, value in candidate.items() if include[key]}


# Arbitrary "other Page state": a page type plus a bag of unrelated page attributes that a
# real Page might carry (slug, title, published flag, section counts, ...). None of this is
# an argument render_page_styles accepts; it exists purely to prove the output is invariant
# to everything EXCEPT the supplied Look_And_Feel_Settings values.
_page_type = st.sampled_from(
    ["application_form", "landing_page", "membership_portal", "unknown_future_page"]
)
_other_page_state = st.dictionaries(
    keys=st.sampled_from(["slug", "title", "published", "section_count", "owner"]),
    values=st.one_of(st.text(max_size=12), st.integers(), st.booleans()),
    max_size=5,
)


class _Page:
    """A minimal stand-in for two different Pages, carrying its own page type + state.

    Only its ``look_and_feel`` values are ever passed to Layer 2; ``page_type`` and
    ``other_state`` model the Page context the generator must prove is irrelevant.
    """

    def __init__(self, look_and_feel, page_type, other_state):
        self.look_and_feel = dict(look_and_feel)
        self.page_type = page_type
        self.other_state = dict(other_state)

    def render(self):
        # Layer 2 receives ONLY the values — never the page type or other state.
        return render_page_styles(self.look_and_feel)


@settings(max_examples=200)
@given(
    values=_settings_values(),
    type_a=_page_type,
    type_b=_page_type,
    state_a=_other_page_state,
    state_b=_other_page_state,
)
def test_identical_values_identical_output_regardless_of_page(
    values, type_a, type_b, state_a, state_b
):
    """Property 2: two Pages with identical values -> identical styling, whatever their
    type or other state.

    Feature: sam-page-look-and-feel, Property 2: For any two Pages supplied identical
    Look_And_Feel_Settings values, render_page_styles SHALL produce identical styling
    output regardless of Page type or any other Page state.
    """
    page_a = _Page(values, type_a, state_a)
    page_b = _Page(values, type_b, state_b)

    styles_a = page_a.render()
    styles_b = page_b.render()

    # Same values -> identical output, even though the two Pages differ in type and in all
    # their other (unrelated) state.
    assert styles_a == styles_b
    assert styles_a.css_variables == styles_b.css_variables
    assert styles_a.page_css == styles_b.page_css
    assert styles_a.font_links == styles_b.font_links
