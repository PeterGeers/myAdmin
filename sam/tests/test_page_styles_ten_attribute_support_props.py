"""
Bugfix spec ``bugfix-published-form-styling`` — Task 8: the PAIRED Layer-2 tests for the
seven→TEN attribute extension (``sam/shared/page_styles`` design §C).

Task 8 (this change) extended the SAM-owned Layer-2 generator so it supports THREE new
values-only attributes on top of the original seven — a deliberate, DOCUMENTED extension of
the exactly-seven set (bugfix 3.4):

  * ``columns``      — DRIVES the application-form grid ``grid-template-columns`` track count;
  * ``logo``         — carried as a supported VALUE the renderer (Task 6) consumes; emits no CSS;
  * ``header_title`` — likewise carried for the renderer; emits no CSS.

These are the PAIRED tests for that generator change (change-with-tests, steering 30/34/39):

  * TEN_ATTRIBUTE_SUPPORT — all ten attributes are accepted (``render_page_styles`` does not
    reject any of them), and a key OUTSIDE the ten is still rejected (bugfix 3.4).
  * COLUMNS_DRIVES_GRID — the authored ``columns`` value changes the grid track count in the
    generated application-form CSS (clamped 1..4 by the generator; authoritative rejection is
    at the edge/service plane, Task 10).
  * LOGO_HEADER_TITLE_CARRIED_NOT_EMITTED — ``logo`` / ``header_title`` are accepted but do NOT
    perturb the generated CSS (the renderer consumes them; the generator emits no CSS for them).
  * REJECT_OUTSIDE_TEN — a key outside the ten raises :class:`UnsupportedAttributeError`.

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

# The original spec-15 seven and the three new bugfix attributes (the documented extension).
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
_NEW_THREE = frozenset({"columns", "logo", "header_title"})
_TEN = _SEVEN | _NEW_THREE


def _normalize(css: str) -> str:
    return re.sub(r"\s+", " ", css).strip().lower()


def _iter_rule_blocks(css: str):
    norm = _normalize(css)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        yield match.group(1).strip(), match.group(2).strip()


def _form_group_track_count(css: str) -> int | None:
    """Base (non-media) grid track count on ``.application-form .form-group``."""
    norm = _normalize(css)
    base = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", norm)
    for selector, body in _iter_rule_blocks(base):
        if ".application-form .form-group" in selector and "grid-template-columns" in body:
            m = re.search(r"repeat\(\s*(\d+)\s*,", body)
            if m:
                return int(m.group(1))
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
# TEN_ATTRIBUTE_SUPPORT — Requirements 2.7 / 3.4
# ══════════════════════════════════════════════════════════════════════════════════════


def test_supported_set_is_exactly_the_ten():
    """``SUPPORTED_ATTRIBUTES`` is exactly the ten — the seven plus the documented extension.

    Validates (bugfix): Requirements 2.7, 3.4
    """
    assert set(SUPPORTED_ATTRIBUTES) == _TEN, (
        "SUPPORTED_ATTRIBUTES must be exactly the ten (seven original + columns/logo/header_title)."
    )
    # The extension is strictly additive — the seven remain supported.
    assert _SEVEN <= set(SUPPORTED_ATTRIBUTES)


def test_all_ten_attributes_accepted_together():
    """A mapping carrying ALL ten attributes renders without rejection (2.7).

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
            "columns": 3,
            "logo": "https://assets.example.org/logo.png",
            "header_title": "Aanmelden bij HDCN",
        }
    )
    assert isinstance(produced, PageStyles)


@settings(max_examples=120)
@given(attribute=st.sampled_from(sorted(_NEW_THREE)))
def test_each_new_attribute_is_individually_accepted(attribute):
    """Each new attribute, authored on its own, is accepted (not rejected as unsupported).

    Validates (bugfix): Requirements 2.7, 3.4
    """
    value = 3 if attribute == "columns" else "x"
    produced = render_page_styles({attribute: value})
    assert isinstance(produced, PageStyles)


# ══════════════════════════════════════════════════════════════════════════════════════
# COLUMNS_DRIVES_GRID — Requirement 2.2
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=150)
@given(columns=st.integers(min_value=1, max_value=4))
def test_columns_drives_grid_track_count(columns):
    """The authored ``columns`` value sets the application-form grid track count (2.2).

    For in-range values (1..4) the generated base ``.form-group`` grid has exactly that many
    tracks — proving ``render_page_styles`` resolves the authored ``columns`` and threads it
    through to the grid (not the fixed default).

    Validates (bugfix): Requirement 2.2
    """
    page_css = render_page_styles({"columns": columns}).page_css
    assert _form_group_track_count(page_css) == columns, (
        f"COLUMNS_DRIVES_GRID (2.2): expected {columns} grid tracks for columns={columns!r}."
    )


@settings(max_examples=100)
@given(columns=st.integers(min_value=-3, max_value=12))
def test_columns_is_defensively_clamped_in_the_grid(columns):
    """Any ``columns`` value is clamped to 1..4 in the generated CSS (defensive floor/ceiling).

    The authoritative out-of-range rejection lives at the edge/service plane (Task 10); the
    generator must always emit a well-formed track list, so an out-of-range value clamps.

    Validates (bugfix): Requirement 2.2
    """
    page_css = render_page_styles({"columns": columns}).page_css
    expected = max(1, min(int(columns), 4))
    assert _form_group_track_count(page_css) == expected


def test_default_columns_used_when_absent():
    """With no ``columns`` authored, the grid uses the SAM-owned multi-column default (3.3).

    Validates (bugfix): Requirements 2.2, 3.4
    """
    page_css = render_page_styles({}).page_css
    tracks = _form_group_track_count(page_css)
    assert tracks is not None and tracks > 1, (
        f"default form grid must be multi-column, got {tracks!r} tracks."
    )


def test_distinct_columns_values_produce_distinct_grids():
    """A change to ``columns`` produces an observable change in the generated grid (2.2 / 2.5).

    Validates (bugfix): Requirement 2.2
    """
    assert _form_group_track_count(render_page_styles({"columns": 2}).page_css) == 2
    assert _form_group_track_count(render_page_styles({"columns": 4}).page_css) == 4


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
# REJECT_OUTSIDE_TEN — Requirement 3.4
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=150)
@given(
    bad_key=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20).filter(
        lambda s: s not in _TEN
    )
)
def test_key_outside_the_ten_is_rejected(bad_key):
    """Any key outside the ten raises ``UnsupportedAttributeError`` (reject-on-unsupported, 3.4).

    Validates (bugfix): Requirement 3.4
    """
    with pytest.raises(UnsupportedAttributeError):
        render_page_styles({bad_key: "x"})


def test_named_unsupported_key_still_rejected():
    """A concrete key outside the ten is rejected, and the error names the offending key (3.4).

    Validates (bugfix): Requirement 3.4
    """
    with pytest.raises(UnsupportedAttributeError) as exc:
        render_page_styles({"totally_unknown_attr": "x", "columns": 2})
    assert exc.value.attribute == "totally_unknown_attr"
