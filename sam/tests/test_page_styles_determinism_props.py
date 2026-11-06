"""
SAM property-based test — Layer-2 **determinism in the settings** (spec 15, task 1.2).

Feature: sam-page-look-and-feel, Property 1: For any valid Look_And_Feel_Settings values
mapping, invoking render_page_styles twice with that same mapping SHALL produce identical
styling output.

Validates: Requirements 1.2, 1.5

What this asserts
-----------------
:func:`sam.shared.page_styles.render_page_styles` (Layer 2, C1) is a PURE function of its
settings mapping: for any valid ``Look_And_Feel_Settings`` values mapping, invoking it twice
with the SAME mapping produces an identical :class:`PageStyles` — identical ``css_variables``,
``page_css``, and ``font_links``. This is the determinism half of Req 1.5 / Req 1.2 (styling
derived solely from, and stable in, the supplied values).

Genuine (non-tautological) strategy
-----------------------------------
The strategy generates only VALID settings mappings over the seven supported attributes
(:data:`sam.shared.page_styles.SUPPORTED_ATTRIBUTES`), so the function never rejects the input
(an unsupported key is Property 5 / task 1.6, not this one). Each attribute is optional (any
subset may be omitted — the absent-attribute default path is still deterministic), and the
"enum-like" attributes draw from BOTH their known value set AND arbitrary free text, so
determinism is exercised across the known-value, fallback-default, and sanitised-value paths
alike. The second call is given a FRESH dict with the same contents (``dict(mapping)``) so a
pass cannot come from the two calls sharing the same object by identity.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.shared` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import render_page_styles

# Known "good" values per attribute, so the strategy exercises the recognised-value paths
# (spacing/radius/shadow lookups, web-font vs system-font branches) as well as free text.
_COLORS = ["#2D5F8A", "#F4A261", "#123456", "#fff", "#000000", "rebeccapurple"]
_FONTS = ["system", "Inter", "Lora", "Roboto", "Open Sans", "Playfair Display"]
_SPACINGS = ["compact", "normal", "relaxed"]
_RADII = ["sharp", "rounded", "pill"]
_SHADOWS = ["none", "subtle", "medium", "dramatic"]


def _value_strategy(known: list[str]) -> st.SearchStrategy:
    """A value drawn from the attribute's known set OR arbitrary free text.

    Free text exercises the default-fallback / sanitiser branches; the known values
    exercise the lookup-map branches. Both must be deterministic.
    """
    return st.one_of(st.sampled_from(known), st.text(max_size=20))


def _settings_strategy() -> st.SearchStrategy:
    """A valid Look_And_Feel_Settings mapping: any subset of the seven supported keys.

    Every key is optional (``st.fixed_dictionaries(..., optional=...)``), so generated
    mappings range from ``{}`` (all defaults) through partial to the full seven — all of
    which are valid input the function must render deterministically.
    """
    return st.fixed_dictionaries(
        {},
        optional={
            "color_primary": _value_strategy(_COLORS),
            "color_accent": _value_strategy(_COLORS),
            "font_heading": _value_strategy(_FONTS),
            "font_body": _value_strategy(_FONTS),
            "base_spacing": _value_strategy(_SPACINGS),
            "border_radius_global": _value_strategy(_RADII),
            "shadow_style": _value_strategy(_SHADOWS),
        },
    )


@settings(max_examples=200)
@given(mapping=_settings_strategy())
def test_render_page_styles_is_deterministic_in_the_settings(mapping):
    """Property 1: twice with the same values -> identical styling output (Req 1.2/1.5)."""
    first = render_page_styles(dict(mapping))
    # A fresh dict with the same contents — a pass cannot come from object identity.
    second = render_page_styles(dict(mapping))

    assert first == second
    assert first.css_variables == second.css_variables
    assert first.page_css == second.page_css
    assert first.font_links == second.font_links
