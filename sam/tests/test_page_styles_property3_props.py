"""
SAM Hypothesis property test (spec 15 / task 1.4) — Property 3 for the Layer-2 CSS
generator :func:`sam.shared.page_styles.render_page_styles`.

Feature: sam-page-look-and-feel, Property 3: For any two values mappings differing in at
least one supported attribute's value, render_page_styles SHALL produce styling that
differs in at least the corresponding styling attribute.

Validates: Requirements 4.2, 5.3

What this proves
----------------
Different values produce *correspondingly* different styling. The property is not merely
"output differs somewhere" — it pins the change to the STYLING ATTRIBUTE that CORRESPONDS
to the changed setting. The seven supported settings map onto the three ``PageStyles``
pieces as follows (from the design C1 / the relocated ``LandingPageStyles`` logic):

- ``color_primary`` / ``color_accent``                       -> ``page_css``
- ``font_heading`` / ``font_body``                           -> ``css_variables`` AND ``font_links``
- ``base_spacing`` / ``border_radius_global`` / ``shadow_style`` -> ``css_variables``

So for each supported attribute we generate TWO distinct valid values, render a baseline
and a one-attribute-mutated settings mapping, and assert the CORRESPONDING ``PageStyles``
piece differs. ≥100 Hypothesis iterations (``max_examples=100``).

The strategies draw ONLY valid, distinct values from each attribute's permitted set
(colours as distinct hex; fonts as distinct web-font names — never ``system``, which emits
no ``<link>`` and shares the system stack; and the enumerated spacing/radius/shadow tokens)
so "differs in at least one attribute" is genuine, and the corresponding-piece assertion is
a real proof of Property 3 rather than "differs somewhere".

Pure, dependency-free: ``render_page_styles`` is stdlib-only (no AWS, no MySQL, no Flask).
"""

import os
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import render_page_styles

# ─── Per-attribute strategies over each attribute's permitted VALUE set ─────────────────
# Each attribute draws a VALID value; the mutation then picks a DISTINCT second value from
# the same set, so the two mappings differ in exactly that one attribute's value.

# A hex colour — the permitted shape for color_primary / color_accent.
_HEX_COLOR = st.from_regex(r"\A#[0-9a-fA-F]{6}\Z")

# A web-font name: a non-blank token that is NOT "system". A real web font (not the system
# stack) so the change is observable in BOTH css_variables (the quoted family) and
# font_links (the Google-Fonts <link>). Kept to plain letters/spaces so it is a clean
# font name (no CSS-injection sanitiser interference).
_WEB_FONT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
    min_size=1,
    max_size=14,
).map(lambda s: s.strip()).filter(lambda s: s and s.lower() != "system")

# The enumerated token sets for the three CSS-variable attributes (the permitted values the
# Layer-2 lookup maps recognise — each distinct token yields distinct CSS).
_SPACING = st.sampled_from(["compact", "normal", "relaxed"])
_RADIUS = st.sampled_from(["sharp", "rounded", "pill"])
_SHADOW = st.sampled_from(["none", "subtle", "medium", "dramatic"])

# attribute -> (value strategy, corresponding PageStyles field names that MUST change).
_ATTRIBUTE_SPECS = {
    "color_primary": (_HEX_COLOR, ("page_css",)),
    "color_accent": (_HEX_COLOR, ("page_css",)),
    "font_heading": (_WEB_FONT, ("css_variables", "font_links")),
    "font_body": (_WEB_FONT, ("css_variables", "font_links")),
    "base_spacing": (_SPACING, ("css_variables",)),
    "border_radius_global": (_RADIUS, ("css_variables",)),
    "shadow_style": (_SHADOW, ("css_variables",)),
}

_SUPPORTED = sorted(_ATTRIBUTE_SPECS)


@st.composite
def _settings_and_mutation(draw):
    """Draw a full baseline settings mapping, an attribute to mutate, and a DISTINCT value.

    Returns ``(baseline, attribute, mutated)`` where ``mutated`` equals ``baseline`` in every
    supported attribute EXCEPT ``attribute``, whose value is a second draw from the same
    permitted set, constrained (via ``assume``) to differ from the baseline's — so the two
    mappings differ in exactly that one attribute's value.
    """
    baseline = {
        attr: draw(value_strategy)
        for attr, (value_strategy, _corr) in _ATTRIBUTE_SPECS.items()
    }

    attribute = draw(st.sampled_from(_SUPPORTED))
    value_strategy, corresponding = _ATTRIBUTE_SPECS[attribute]

    new_value = draw(value_strategy)
    # Values must genuinely differ (case-insensitively for fonts, since "system" is the only
    # case-folded special and web fonts here are case-sensitive family names — but two family
    # names differing only in case would still render different quoted families, so a plain
    # inequality is the right "differs in value" test).
    assume(new_value != baseline[attribute])

    mutated = dict(baseline)
    mutated[attribute] = new_value
    return baseline, attribute, mutated, corresponding


@settings(max_examples=100)
@given(_settings_and_mutation())
def test_property_3_different_values_produce_different_corresponding_styling(case):
    """Feature: sam-page-look-and-feel, Property 3: For any two values mappings differing in at least one supported attribute's value, render_page_styles SHALL produce styling that differs in at least the corresponding styling attribute.

    Validates: Requirements 4.2, 5.3
    """
    baseline, attribute, mutated, corresponding = case

    base_styles = render_page_styles(baseline)
    mutated_styles = render_page_styles(mutated)

    # The two mappings differ in exactly one attribute's value...
    assert baseline[attribute] != mutated[attribute]
    assert {k: baseline[k] for k in baseline if k != attribute} == {
        k: mutated[k] for k in mutated if k != attribute
    }

    # ...and the styling differs in AT LEAST the CORRESPONDING styling attribute (Property 3).
    changed_pieces = {
        field
        for field in ("css_variables", "page_css", "font_links")
        if getattr(base_styles, field) != getattr(mutated_styles, field)
    }
    for expected_field in corresponding:
        assert expected_field in changed_pieces, (
            f"changing {attribute!r} ({baseline[attribute]!r} -> {mutated[attribute]!r}) "
            f"must change PageStyles.{expected_field}; changed pieces were {sorted(changed_pieces)}"
        )
