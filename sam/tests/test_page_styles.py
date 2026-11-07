"""
SAM unit tests for the Layer-2 CSS generator —
:func:`sam.shared.page_styles.render_page_styles` (spec 15 / DD-1, task 1.1).

These pin the task's observable contract: the ONE reusable function (C1) exposing a
``PageStyles`` carrying the ``:root`` variables block, the page CSS, and the font
``<link>`` tags; exactly the seven supported attributes; absent attribute -> SAM-owned
default; unsupported attribute -> ``UnsupportedAttributeError`` and NO styling;
page-type-agnostic (no Application_Form-specific state); and the DEPENDENCY-FREE /
no-Flask-runtime guarantee (static source check).

The Hypothesis property tests (Properties 1-5) are the SEPARATE tasks 1.2-1.6; this file
is the minimal land-with-a-unit-test companion for the extraction (steering 34 / the
change-with-tests contract).

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2, 6.3
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import (
    SUPPORTED_ATTRIBUTES,
    PageStyles,
    UnsupportedAttributeError,
    render_page_styles,
)

# The seven supported attributes with a full, valid value for each (Req 3.2).
_FULL_SETTINGS = {
    "color_primary": "#2D5F8A",
    "color_accent": "#F4A261",
    "font_heading": "Inter",
    "font_body": "Lora",
    "base_spacing": "relaxed",
    "border_radius_global": "pill",
    "shadow_style": "dramatic",
}


def test_supported_attributes_are_exactly_the_seven():
    """Req 3.2 + bugfix 3.4: the capability supports EXACTLY the nine named attributes.

    The original spec-15 contract was exactly seven; the bugfix ``bugfix-published-form-styling``
    (Task 8) extended it with two values-only attributes — ``logo`` and ``header_title``
    (carried for the renderer) — a deliberate, documented extension (bugfix 3.4). The earlier
    ``columns`` attribute was later removed (the form grid is now fully width-driven), so the
    set is now exactly these nine.
    """
    assert SUPPORTED_ATTRIBUTES == frozenset(
        {
            "color_primary",
            "color_accent",
            "font_heading",
            "font_body",
            "base_spacing",
            "border_radius_global",
            "shadow_style",
            # bugfix bugfix-published-form-styling (Task 8) — the documented extension.
            # (The earlier ``columns`` attribute was removed — the form grid is now fully
            # width-driven, so an authored column count has no effect.)
            "logo",
            "header_title",
        }
    )


def test_render_returns_pagestyles_with_three_css_pieces():
    """C1: PageStyles carries the :root variables block, the page CSS, and font links."""
    styles = render_page_styles(_FULL_SETTINGS)

    assert isinstance(styles, PageStyles)
    # :root variables block (former build_css_variables)
    assert styles.css_variables.startswith(":root {")
    assert styles.css_variables.rstrip().endswith("}")
    assert "--font-heading:" in styles.css_variables
    assert "--shadow-card:" in styles.css_variables
    # page CSS (former build_page_css) — carries the brand colours
    assert "#2D5F8A" in styles.page_css
    assert "#F4A261" in styles.page_css
    # font links (former build_font_links) — web fonts selected, so <link> tags present
    assert '<link href="https://fonts.googleapis.com/css2?family=' in styles.font_links


def test_values_flow_into_the_generated_css():
    """Req 1.2: styling is derived solely from the supplied values."""
    styles = render_page_styles(_FULL_SETTINGS)

    # base_spacing=relaxed -> --spacing-section: 3rem
    assert "--spacing-section: 3rem;" in styles.css_variables
    # border_radius_global=pill -> --radius-lg: 9999px
    assert "--radius-lg: 9999px;" in styles.css_variables
    # shadow_style=dramatic -> its card shadow
    assert "0 8px 24px rgba(0,0,0,0.2)" in styles.css_variables
    # font_heading=Inter, font_body=Lora -> quoted families
    assert '"Inter", sans-serif' in styles.css_variables
    assert '"Lora", sans-serif' in styles.css_variables


def test_determinism_identical_settings_identical_output():
    """Req 1.5: identical settings produce identical output."""
    a = render_page_styles(dict(_FULL_SETTINGS))
    b = render_page_styles(dict(_FULL_SETTINGS))
    assert a == b


def test_absent_attributes_fall_back_to_sam_owned_defaults():
    """Req 1.3 / 3.3 / 4.4 / 5.4: an empty settings map renders with defaults, no failure."""
    styles = render_page_styles({})

    assert isinstance(styles, PageStyles)
    # default font_heading/body == "system" -> the system font stack, no quoted family
    assert "-apple-system" in styles.css_variables
    # default base_spacing=normal -> --spacing-section: 2rem
    assert "--spacing-section: 2rem;" in styles.css_variables
    # default border_radius_global=rounded -> --radius-md: 8px
    assert "--radius-md: 8px;" in styles.css_variables
    # default shadow_style=subtle
    assert "0 2px 8px rgba(0,0,0,0.08)" in styles.css_variables
    # default brand colours (the professional theme)
    assert "#2D5F8A" in styles.page_css
    assert "#F4A261" in styles.page_css
    # system fonts -> no font <link> tags
    assert styles.font_links == ""


def test_partial_settings_use_defaults_for_the_rest():
    """Req 1.3 / 3.3: a partial map uses defaults for every unset attribute without failing."""
    styles = render_page_styles({"color_primary": "#123456"})

    assert "#123456" in styles.page_css
    # the rest fall back to defaults
    assert "--spacing-section: 2rem;" in styles.css_variables  # normal
    assert styles.font_links == ""  # system fonts


def test_unsupported_attribute_is_rejected_and_names_the_key():
    """Req 3.4: an unsupported key raises and names the offending attribute."""
    with pytest.raises(UnsupportedAttributeError) as excinfo:
        render_page_styles({"color_primary": "#fff", "bogus_attr": "x"})

    assert excinfo.value.attribute == "bogus_attr"
    assert "bogus_attr" in str(excinfo.value)


def test_unsupported_attribute_produces_no_styling():
    """Req 3.4: when rejected, no PageStyles is produced (the raise is the whole result)."""
    produced = None
    try:
        produced = render_page_styles({"not_a_real_attr": "x"})
    except UnsupportedAttributeError:
        pass
    assert produced is None


def test_page_type_agnostic_same_values_same_output():
    """Req 6.1 / 6.2 / 6.3: output depends only on the supplied values, not any page type.

    render_page_styles takes NO page-type argument; two callers (e.g. application form vs a
    future landing page) supplying the same values get identical output.
    """
    application_form_call = render_page_styles(dict(_FULL_SETTINGS))
    landing_page_call = render_page_styles(dict(_FULL_SETTINGS))
    assert application_form_call == landing_page_call


def test_different_values_produce_different_styling():
    """Req 4.2 / 5.3: a change in a supported value changes the styling output."""
    base = render_page_styles({"color_primary": "#111111"})
    changed = render_page_styles({"color_primary": "#999999"})
    assert base.page_css != changed.page_css


def test_render_page_styles_is_dependency_free_stdlib_only():
    """Req 3.1 / 3.5 / 2.2: the module imports ONLY stdlib (no Flask/boto3/DB/SAM/backend).

    Proving the SAM-owned styling logic has no Flask-plane dependency and cannot make a
    runtime call to the Flask plane — it is pure, stdlib-only code.
    """
    import ast

    allowed = {"re", "typing", "collections", "dataclasses"}

    src_path = os.path.join(_REPO_ROOT, "sam", "shared", "page_styles", "__init__.py")
    with open(src_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported_roots.add(node.module.split(".")[0])

    disallowed = imported_roots - allowed
    assert not disallowed, f"page_styles must be stdlib-only; found: {sorted(disallowed)}"


# ─── Property 5 (task 1.6) — unsupported attribute is rejected, no styling ──────────────
# Hypothesis property test for the Look_And_Feel_Capability's Layer-2 rejection contract.
# This is the separate property task that complements the example-based
# `test_unsupported_attribute_*` unit tests above.

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

# A value that is never one of the seven supported attribute NAMES. We draw unsupported
# keys from arbitrary text, then exclude the supported set so every generated mapping is
# guaranteed to carry at least one unsupported key (the precondition of Property 5).
_unsupported_key = st.text(min_size=1, max_size=40).filter(
    lambda k: k not in SUPPORTED_ATTRIBUTES
)

# Arbitrary scalar values the keys may carry — the value is irrelevant to rejection, which
# keys on the attribute NAME alone (Req 3.4).
_any_value = st.one_of(
    st.text(max_size=20),
    st.integers(),
    st.booleans(),
    st.none(),
)

# A valid supported-attribute subset, so we also cover the realistic case where some
# legitimate keys sit alongside the offending one.
_supported_subset = st.dictionaries(
    keys=st.sampled_from(sorted(SUPPORTED_ATTRIBUTES)),
    values=st.text(min_size=1, max_size=20),
    max_size=len(SUPPORTED_ATTRIBUTES),
)


@settings(max_examples=200)
@given(
    supported=_supported_subset,
    unsupported=st.dictionaries(
        keys=_unsupported_key,
        values=_any_value,
        min_size=1,
        max_size=4,
    ),
)
def test_property_5_unsupported_attribute_rejected_and_no_styling(supported, unsupported):
    """Feature: sam-page-look-and-feel, Property 5: For any values mapping containing a key that is not one of the seven supported attributes, render_page_styles SHALL reject the request, signal the unsupported attribute, and produce no Page styling.

    Validates: Requirements 3.4

    For any mapping carrying at least one key outside the seven SUPPORTED_ATTRIBUTES,
    render_page_styles must:
      - REJECT the request (raise UnsupportedAttributeError),
      - SIGNAL the offending key (the raised error names an actual unsupported key), and
      - produce NO Page styling (no PageStyles value escapes the call).
    """
    # Merge a (possibly empty) valid subset with the guaranteed-unsupported keys. Keys are
    # disjoint by construction (_unsupported_key excludes the supported set), so the merged
    # mapping always contains every unsupported key.
    values = {**supported, **unsupported}

    produced = None
    with pytest.raises(UnsupportedAttributeError) as excinfo:
        produced = render_page_styles(values)

    # Produce NO Page styling — nothing was returned before the raise.
    assert produced is None

    # Signal the unsupported attribute — the reported key is an actual unsupported key
    # present in the mapping (never a supported one), and it is named in the message. The
    # message renders the key via repr() (`{attribute!r}`), so a non-printable key like a
    # control char appears as its escaped repr; assert against repr() to stay correct for
    # ANY generated key, not only printable ones.
    offending = excinfo.value.attribute
    assert offending in unsupported
    assert offending not in SUPPORTED_ATTRIBUTES
    assert repr(offending) in str(excinfo.value)
