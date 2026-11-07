"""
Bugfix spec ``bugfix-published-form-styling`` — Task 8: the PAIRED Layer-2 tests for the
seven→NINE attribute extension (``sam/shared/page_styles`` design §C).

Task 8 extended the SAM-owned Layer-2 generator so it supports TWO new values-only attributes
on top of the original seven — a deliberate, DOCUMENTED extension of the exactly-seven set
(bugfix 3.4):

  * ``logo``         — carried as a supported VALUE the renderer (Task 6) consumes; emits no CSS;
  * ``header_title`` — likewise carried for the renderer; emits no CSS.

(The earlier ``columns`` attribute was later REMOVED: the application-form field-group grid is
now a fully WIDTH-DRIVEN responsive ``auto-fit`` grid — more columns on a wide container, one on
a narrow one — so an authored column count has no effect and is no longer a settable attribute.
A legacy stored ``columns`` is TOLERATED (stripped/ignored) by ``render_page_styles`` so an
existing stored row never fails to publish.)

These are the PAIRED tests for that generator change (change-with-tests, steering 30/34/39):

  * NINE_ATTRIBUTE_SUPPORT — all nine attributes are accepted (``render_page_styles`` does not
    reject any of them), and a key OUTSIDE the nine is still rejected (bugfix 3.4).
  * WIDTH_DRIVEN_GRID — the form-group grid is a width-driven ``auto-fit`` grid (no authored
    track count; reflows purely by container width).
  * LOGO_HEADER_TITLE_CARRIED_NOT_EMITTED — ``logo`` / ``header_title`` are accepted but do NOT
    perturb the generated CSS (the renderer consumes them; the generator emits no CSS for them).
  * LEGACY_COLUMNS_TOLERATED — a legacy stored ``columns`` is stripped/ignored, not rejected.
  * REJECT_OUTSIDE_NINE — a key outside the nine raises :class:`UnsupportedAttributeError`.

Validates (bugfix): Requirements 2.2, 2.7, 3.4

Property-based (Hypothesis ≥100 iterations). No boto3 / no AWS — pure generator functions only.
"""

from __future__ import annotations

import os
import re
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import (  # noqa: E402
    SUPPORTED_ATTRIBUTES,
    PageStyles,
    UnsupportedAttributeError,
    render_page_styles,
)

# The original spec-15 seven and the two new bugfix attributes (the documented extension).
_SEVEN = frozenset(
    {
        "color_primary",
        "color_accent",
        "font_heading",
        "font_body",
        "base_spacing",
        "border_radius_global",
        "shadow_style",
    }
)
_NEW_TWO = frozenset({"logo", "header_title"})
_NINE = _SEVEN | _NEW_TWO


def _normalize(css: str) -> str:
    return re.sub(r"\s+", " ", css).strip().lower()


def _iter_rule_blocks(css: str):
    norm = _normalize(css)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        yield match.group(1).strip(), match.group(2).strip()


def _form_group_is_width_driven_auto_fit(css: str) -> bool:
    """True iff the base (non-media) ``.application-form .form-group`` grid is a width-driven
    ``auto-fit`` grid (``repeat(auto-fit, minmax(...))``) — reflows by container width with no
    authored track count."""
    norm = _normalize(css)
    base = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", norm)
    for selector, body in _iter_rule_blocks(base):
        if ".application-form .form-group" in selector and "grid-template-columns" in body:
            if re.search(r"auto-fit,\s*minmax\(", body):
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════════════════
# NINE_ATTRIBUTE_SUPPORT — Requirements 2.7 / 3.4
# ══════════════════════════════════════════════════════════════════════════════════════


def test_supported_set_is_exactly_the_ten():
    """``SUPPORTED_ATTRIBUTES`` is exactly the nine — the seven plus the documented extension.

    Validates (bugfix): Requirements 2.7, 3.4
    """
    assert set(SUPPORTED_ATTRIBUTES) == _NINE, (
        "SUPPORTED_ATTRIBUTES must be exactly the nine (seven original + logo/header_title)."
    )
    # The extension is strictly additive — the seven remain supported.
    assert _SEVEN <= set(SUPPORTED_ATTRIBUTES)


def test_all_ten_attributes_accepted_together():
    """A mapping carrying ALL nine attributes renders without rejection (2.7).

    Validates (bugfix): Requirements 2.7, 3.4
    """
    produced = render_page_styles(
        {
            "color_primary": "#C01030",
            "color_accent": "#0A7E3F",
            "font_heading": "Inter",
            "font_body": "Lora",
            "base_spacing": "relaxed",
            "border_radius_global": "pill",
            "shadow_style": "dramatic",
            "logo": "https://assets.example.org/logo.png",
            "header_title": "Aanmelden bij HDCN",
        }
    )
    assert isinstance(produced, PageStyles)


@settings(max_examples=120)
@given(attribute=st.sampled_from(sorted(_NEW_TWO)))
def test_each_new_attribute_is_individually_accepted(attribute):
    """Each new attribute, authored on its own, is accepted (not rejected as unsupported).

    Validates (bugfix): Requirements 2.7, 3.4
    """
    produced = render_page_styles({attribute: "x"})
    assert isinstance(produced, PageStyles)


# ══════════════════════════════════════════════════════════════════════════════════════
# WIDTH_DRIVEN_GRID — Requirement 2.2
# ══════════════════════════════════════════════════════════════════════════════════════


def test_form_group_grid_is_width_driven_auto_fit():
    """The form-group grid is a width-driven ``auto-fit`` grid — no authored track count; it
    reflows purely by container width (more columns on a wide screen, one on a narrow one).

    Validates (bugfix): Requirement 2.2
    """
    page_css = render_page_styles({}).page_css
    assert _form_group_is_width_driven_auto_fit(page_css), (
        "WIDTH_DRIVEN_GRID (2.2): the form-group grid must be a repeat(auto-fit, minmax(...)) grid."
    )


def test_width_driven_grid_is_independent_of_authored_values():
    """The grid rule does not depend on any authored look-and-feel value — it is the SAME
    width-driven auto-fit grid regardless of colours / fonts (2.2 / 2.5).

    Validates (bugfix): Requirement 2.2
    """
    a = render_page_styles({}).page_css
    b = render_page_styles(
        {"color_primary": "#C01030", "logo": "https://x/y.png", "header_title": "Hi"}
    ).page_css
    assert _form_group_is_width_driven_auto_fit(a)
    assert _form_group_is_width_driven_auto_fit(b)


# ══════════════════════════════════════════════════════════════════════════════════════
# LEGACY_COLUMNS_TOLERATED — backward compatibility
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(columns=st.integers(min_value=-3, max_value=12))
def test_legacy_columns_is_tolerated_and_ignored(columns):
    """A legacy stored ``columns`` value (from an earlier version) is stripped/ignored, NOT
    rejected — so an existing stored look-and-feel row never fails to publish. The generated CSS
    is identical to one with no ``columns`` authored (the grid is width-driven regardless).

    Validates (bugfix): backward compatibility (legacy ``columns`` tolerated)
    """
    baseline = render_page_styles({})
    with_legacy = render_page_styles({"columns": columns})
    assert with_legacy.page_css == baseline.page_css
    assert with_legacy.css_variables == baseline.css_variables
    assert _form_group_is_width_driven_auto_fit(with_legacy.page_css)


# ══════════════════════════════════════════════════════════════════════════════════════
# LOGO_HEADER_TITLE_CARRIED_NOT_EMITTED — Requirement 2.7
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=100)
@given(
    logo=st.text(max_size=60),
    header_title=st.text(max_size=60),
)
def test_logo_and_header_title_do_not_change_generated_css(logo, header_title):
    """``logo`` / ``header_title`` are supported VALUES but emit NO CSS — the generator output
    is identical to one with neither authored (the renderer consumes them, Task 6).

    Validates (bugfix): Requirement 2.7
    """
    baseline = render_page_styles({})
    with_values = render_page_styles({"logo": logo, "header_title": header_title})

    assert with_values.css_variables == baseline.css_variables
    assert with_values.page_css == baseline.page_css
    assert with_values.font_links == baseline.font_links


# ══════════════════════════════════════════════════════════════════════════════════════
# REJECT_OUTSIDE_NINE — Requirement 3.4
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=150)
@given(
    bad_key=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20).filter(
        lambda s: s not in _NINE and s != "columns"
    )
)
def test_key_outside_the_ten_is_rejected(bad_key):
    """Any key outside the nine (and not the tolerated legacy ``columns``) raises
    ``UnsupportedAttributeError`` (reject-on-unsupported, 3.4).

    Validates (bugfix): Requirement 3.4
    """
    with pytest.raises(UnsupportedAttributeError):
        render_page_styles({bad_key: "x"})


def test_named_unsupported_key_still_rejected():
    """A concrete key outside the nine is rejected, and the error names the offending key (3.4).

    Validates (bugfix): Requirement 3.4
    """
    with pytest.raises(UnsupportedAttributeError) as exc:
        render_page_styles({"totally_unknown_attr": "x"})
    assert exc.value.attribute == "totally_unknown_attr"
