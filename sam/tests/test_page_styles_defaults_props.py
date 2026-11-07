"""
SAM property-based test — Property 4 for the Layer-2 CSS generator
:func:`sam.shared.page_styles.render_page_styles` (spec 15 / task 1.5).

Feature: sam-page-look-and-feel, Property 4: For any values mapping with any subset of the
supported attributes omitted, render_page_styles SHALL produce styling using the SAM-owned
default for each omitted attribute and SHALL NOT fail.

Validates: Requirements 1.3, 3.3, 4.4, 5.4

What this asserts (genuine, non-tautological)
---------------------------------------------
Property 4 is the defaulting guarantee: an absent attribute must transparently resolve to the
Layer-2 SAM-owned default, and no absence (not even the empty mapping) may cause a failure.

The strategy draws a VALID value for each of the seven supported attributes and then drops an
arbitrary SUBSET of those keys (the empty mapping and the full mapping are both reachable). For
each generated mapping the test asserts two things:

1. **SHALL NOT fail** — ``render_page_styles`` returns a ``PageStyles`` for every subset,
   including ``{}``. Any raised exception fails the property.
2. **SAM-owned default for each omitted attribute** — the output of the partial mapping is
   IDENTICAL to the output of the same mapping with every omitted key filled in from the
   module's ``_DEFAULTS`` map. Because ``render_page_styles`` is deterministic in its values
   (Property 1), equality to the explicitly-defaulted mapping is exactly "the omitted attribute
   used its default" — not a tautology (the partial and the filled mapping are different input
   dicts; they coincide in output only because the omitted keys defaulted).

The expected-default reference is the module's own ``_DEFAULTS`` (the single SAM-owned source of
the default values), so the test pins behaviour to the real defaults rather than re-encoding
literals that could drift.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared import page_styles as ps
from sam.shared.page_styles import (
    SUPPORTED_ATTRIBUTES,
    PageStyles,
    render_page_styles,
)

# A pool of VALID values per supported attribute. Colours/fonts include arbitrary-but-safe
# tokens; the enumerated attributes draw from their real permitted vocabularies (the lookup-map
# keys the generator recognises) PLUS values outside the maps — the generator falls back to its
# own map default for an unrecognised enumerated value, which is still a non-failing render, so
# any supplied value is a valid "present" value for Property 4's purposes.
_VALUE_POOL = {
    "color_primary": st.sampled_from(["#2D5F8A", "#123456", "#ff0000", "#abcdef"]),
    "color_accent": st.sampled_from(["#F4A261", "#000000", "#00ff00", "#654321"]),
    "font_heading": st.sampled_from(["system", "Inter", "Lora", "Roboto"]),
    "font_body": st.sampled_from(["system", "Inter", "Lora", "Open Sans"]),
    "base_spacing": st.sampled_from(["compact", "normal", "relaxed"]),
    "border_radius_global": st.sampled_from(["sharp", "rounded", "pill"]),
    "shadow_style": st.sampled_from(["none", "subtle", "medium", "dramatic"]),
    # bugfix bugfix-published-form-styling (Task 8): the two new values-only attributes are
    # now supported, so the defaults/omission property must cover them too (each has a SAM-owned
    # default the omission path falls back to — logo / header_title -> empty). Valid "present"
    # values below. (The earlier ``columns`` attribute was removed — the form grid is now fully
    # width-driven, so there is no column count to default.)
    "logo": st.sampled_from(["https://assets.example.org/logo.png", "logo.svg"]),
    "header_title": st.sampled_from(["Aanmelden", "Join us"]),
}

# Sanity: the pool covers EXACTLY the supported attributes (now ten), so if the supported set
# ever changes this test fails loudly rather than silently under-covering.
assert set(_VALUE_POOL) == set(SUPPORTED_ATTRIBUTES)


@st.composite
def _partial_settings(draw):
    """Draw a settings mapping with an ARBITRARY SUBSET of the seven attributes omitted.

    First draws a valid value for every supported attribute, then keeps a random subset of the
    keys (``min_size=0`` so the empty mapping — all attributes omitted — is reachable, and the
    full mapping — none omitted — is reachable too).
    """
    full = {attr: draw(strategy) for attr, strategy in _VALUE_POOL.items()}
    kept_keys = draw(
        st.lists(
            st.sampled_from(sorted(SUPPORTED_ATTRIBUTES)),
            unique=True,
            min_size=0,
            max_size=len(SUPPORTED_ATTRIBUTES),
        )
    )
    return {k: full[k] for k in kept_keys}


@settings(max_examples=200)
@given(partial=_partial_settings())
def test_property_absent_attributes_fall_back_to_defaults_without_failing(partial):
    """Feature: sam-page-look-and-feel, Property 4: For any values mapping with any subset of
    the supported attributes omitted, render_page_styles SHALL produce styling using the
    SAM-owned default for each omitted attribute and SHALL NOT fail.

    Validates: Requirements 1.3, 3.3, 4.4, 5.4
    """
    # 1. SHALL NOT fail — a partial (or empty) mapping always produces PageStyles.
    produced = render_page_styles(partial)
    assert isinstance(produced, PageStyles)

    # 2. SAM-owned default for each omitted attribute — filling every omitted key from the
    #    module's own _DEFAULTS yields IDENTICAL output. Equality here means the omitted keys
    #    defaulted (render is deterministic in its values, Property 1); the two inputs are
    #    different dicts, so this is not a tautology.
    explicitly_defaulted = dict(partial)
    for attr in SUPPORTED_ATTRIBUTES:
        if attr not in explicitly_defaulted:
            explicitly_defaulted[attr] = ps._DEFAULTS[attr]

    assert produced == render_page_styles(explicitly_defaulted)
