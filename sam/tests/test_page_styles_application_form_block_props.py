"""
Bugfix spec ``bugfix-published-form-styling`` — Task 5.2: the PAIRED Layer-2 tests for the
Task-5.1 application-form CSS block (``sam/shared/page_styles`` DD-B1).

Task 5.1 (already implemented) extended the SAM-owned Layer-2 generator so the PUBLISHED
application form genuinely carries the tenant's look-and-feel on the form's OWN elements:

  * ``--color-primary`` / ``--color-accent`` added to the ``:root`` variables block;
  * a new ``.application-form`` CSS block (:func:`_build_application_form_css`) emitted AFTER
    the whole existing page CSS, that
      - themes the form's OWN elements with the brand colours — the form heading / title
        (``.application-form h1`` / ``.application-form .form-title`` / ``.application-form h2``),
        the submit ``button[type="submit"]`` (background = primary, hover = accent), and the
        input / select / textarea ``:focus`` state;
      - lays the ``.form-group`` field containers out in a MULTI-COLUMN grid
        (``grid-template-columns: repeat(N, 1fr)``, default 2, clamped 1..4) that COLLAPSES to
        a single column under an ``@media (max-width: 480px)`` breakpoint.

These are the PAIRED tests for that generator change (change-with-tests, steering 30/34/39).
They assert the generated CSS at the SOURCE (the generator), complementing the Task-1
bug-condition test that asserts the APPLIED result in the baked artifact. The key assertions:

  * BRAND_COLOURS_ON_FORM_OWN_ELEMENTS (2.1) — the resolved brand colour must appear INSIDE a
    CSS rule whose selector targets an ``.application-form`` OWN element (the heading/title, the
    submit button, or the input/select/textarea ``:focus`` state) — not merely somewhere in the
    stylesheet (the false-parity gap). Checked by parsing rule blocks, so a colour that only
    themes landing classes does NOT satisfy it.
  * MULTI_COLUMN_COLLAPSING_GRID (2.2) — a grid of >1 track is defined on the form's own
    ``.form-group`` container, AND a small-screen media query collapses that same container to a
    single column.
  * LANDING_CSS_BYTE_IDENTICAL (3.7) — the landing-class CSS block is byte-identical to the
    Task-3 baseline snapshot (``fixtures/landing_classes_styling_bugfix_snapshot.json``), so the
    additive form block never perturbs a future SAM landing page.

Validates (bugfix): Requirements 2.1, 2.2, 3.7

Property-based (Hypothesis >=100 iterations) over distinct brand colours / column counts, plus
the fixed landing-snapshot golden. No boto3 / no AWS — pure generator functions only.
"""

from __future__ import annotations

import json
import os
import re
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import (  # noqa: E402
    _build_application_form_css,
    _build_page_css,
    render_page_styles,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
_LANDING_SNAPSHOT = os.path.join(
    _FIXTURES, "landing_classes_styling_bugfix_snapshot.json"
)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _normalize(css: str) -> str:
    """Collapse whitespace so rule/selector matching is layout-insensitive."""
    return re.sub(r"\s+", " ", css).strip().lower()


def _rule_lines(css: str) -> list[str]:
    return [ln.strip() for ln in css.splitlines() if ln.strip()]


def _iter_rule_blocks(css: str):
    """Yield ``(selector, body)`` for each ``selector { body }`` rule block (normalised)."""
    norm = _normalize(css)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        yield match.group(1).strip(), match.group(2).strip()


# Own-element selectors for the FORM itself (not the landing classes). A brand colour that
# lands in one of these rule bodies is genuinely applied to the form's own appearance.
_FORM_OWN_SELECTORS = (
    ".application-form h1",
    ".application-form h2",
    ".application-form .form-title",
    'button[type="submit"]',
    ".application-form input:focus",
    ".application-form select:focus",
    ".application-form textarea:focus",
)


def _colour_applied_to_form_own_element(css: str, colour: str) -> bool:
    """True iff ``colour`` appears INSIDE a rule targeting an ``.application-form`` own element."""
    colour = colour.lower()
    for selector, body in _iter_rule_blocks(css):
        if colour in body and any(sel in selector for sel in _FORM_OWN_SELECTORS):
            return True
    return False


def _form_group_track_count(css: str) -> int | None:
    """Return the base (non-media) grid track count on ``.application-form .form-group``.

    Parses the top-level ``.form-group`` rule (the one NOT inside an ``@media`` block). Returns
    ``None`` if no such multi-track grid rule is found.
    """
    norm = _normalize(css)
    # Strip the media-query blocks so we read the BASE .form-group rule, not the collapse rule.
    base = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", norm)
    for selector, body in _iter_rule_blocks(base):
        if ".application-form .form-group" in selector and "grid-template-columns" in body:
            m = re.search(r"repeat\(\s*(\d+)\s*,", body)
            if m:
                return int(m.group(1))
    return None


def _grid_collapses_to_single_column(css: str) -> bool:
    """True iff a small-screen media query collapses ``.form-group`` to a single column."""
    norm = _normalize(css)
    for media in re.finditer(r"@media[^{]*max-width[^{]*\{(.*?)\}\s*\}", norm):
        block = media.group(1)
        if ".application-form .form-group" in block or ".form-group" in block:
            if re.search(r"grid-template-columns:\s*(1fr|none)\b", block):
                return True
    return False


# ── Strategies ────────────────────────────────────────────────────────────────────────

# Vivid brand colours DISTINCT from the SAM defaults, so "applied" is observable.
_COLOURS = st.sampled_from(
    ["#c01030", "#7b2cbf", "#0a7e3f", "#d62828", "#1d3557", "#e63946", "#2d5f8a"]
)
# `columns` is clamped to 1..4 by the generator; exercise below, in, and above the range.
_COLUMNS = st.integers(min_value=-2, max_value=8)


# ══════════════════════════════════════════════════════════════════════════════════════
# BRAND_COLOURS_ON_FORM_OWN_ELEMENTS — Requirement 2.1
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=150)
@given(primary=_COLOURS, accent=_COLOURS, columns=_COLUMNS)
def test_brand_colour_applied_to_form_own_elements(primary, accent, columns):
    """The primary brand colour reaches the form's OWN elements (heading/title/submit/focus).

    The colour must appear INSIDE a rule whose selector targets an ``.application-form`` own
    element — not merely somewhere in the stylesheet (closing the false-parity gap that hid the
    bug). The accent colour themes the submit-button hover.

    Validates (bugfix): Requirement 2.1
    """
    block = _build_application_form_css(primary, accent, columns)

    assert _colour_applied_to_form_own_element(block, primary), (
        f"BRAND_COLOURS_ON_FORM_OWN_ELEMENTS (2.1): primary {primary!r} is NOT applied to any "
        f"form own-element rule (heading/title/submit/focus). columns={columns!r}"
    )

    # The submit button carries the primary background and the accent on hover.
    submit_bg = False
    submit_hover_accent = False
    for selector, body in _iter_rule_blocks(block):
        if 'button[type="submit"]' in selector:
            if ":hover" in selector:
                submit_hover_accent = accent.lower() in body
            else:
                submit_bg = primary.lower() in body
    assert submit_bg, (
        f"BRAND_COLOURS (2.1): submit button must carry the primary colour {primary!r} as its "
        "background."
    )
    assert submit_hover_accent, (
        f"BRAND_COLOURS (2.1): submit button hover must carry the accent colour {accent!r}."
    )


@settings(max_examples=150)
@given(primary=_COLOURS, accent=_COLOURS)
def test_full_generator_applies_brand_colour_to_form_via_render_page_styles(primary, accent):
    """End-to-end through ``render_page_styles``: the produced ``page_css`` themes the form.

    Exercises the real public entry (not just the private block builder) so the thread-through
    from :func:`render_page_styles` -> :func:`_build_page_css` -> :func:`_build_application_form_css`
    is covered. The resolved primary colour must reach an ``.application-form`` own element.

    Validates (bugfix): Requirement 2.1
    """
    page_css = render_page_styles(
        {"color_primary": primary, "color_accent": accent}
    ).page_css
    assert _colour_applied_to_form_own_element(page_css, primary), (
        f"BRAND_COLOURS (2.1): render_page_styles output does not apply primary {primary!r} to a "
        "form own-element rule."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# MULTI_COLUMN_COLLAPSING_GRID — Requirement 2.2
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=150)
@given(primary=_COLOURS, accent=_COLOURS, columns=_COLUMNS)
def test_form_group_grid_is_multi_column_and_clamped(primary, accent, columns):
    """The form groups lay out in a grid whose track count is the clamped (1..4) column value.

    The generator clamps ``columns`` to 1..4 so it always emits a well-formed track list. We
    assert the base ``.form-group`` rule is a grid with that clamped track count.

    Validates (bugfix): Requirement 2.2
    """
    block = _build_application_form_css(primary, accent, columns)
    expected = max(1, min(int(columns), 4))

    tracks = _form_group_track_count(block)
    assert tracks == expected, (
        f"MULTI_COLUMN_COLLAPSING_GRID (2.2): .form-group grid track count {tracks!r} != clamped "
        f"expected {expected!r} for columns={columns!r}."
    )


@settings(max_examples=100)
@given(primary=_COLOURS, accent=_COLOURS, columns=st.integers(min_value=2, max_value=8))
def test_multi_column_grid_collapses_to_single_column_on_small_screens(
    primary, accent, columns
):
    """A multi-column grid (columns>=2 -> clamped to 2..4) collapses to one column on small screens.

    For a multi-column choice the base rule has >1 track AND a small-screen media query collapses
    ``.form-group`` to a single column (mirroring the landing-grid ``@media (max-width: 480px)``
    collapse pattern).

    Validates (bugfix): Requirement 2.2
    """
    block = _build_application_form_css(primary, accent, columns)

    tracks = _form_group_track_count(block)
    assert tracks is not None and tracks > 1, (
        f"MULTI_COLUMN (2.2): expected a >1-track base grid for columns={columns!r}, got {tracks!r}."
    )
    assert _grid_collapses_to_single_column(block), (
        "MULTI_COLUMN (2.2): the multi-column grid must collapse to a single column under a "
        "small-screen media query."
    )


def test_form_group_default_columns_is_multi_column_collapsing():
    """With no explicit columns, the form grid defaults to multi-column and still collapses.

    ``_build_page_css`` (and ``render_page_styles``) call the form-block builder with the default
    column count (2) until the ``columns`` attribute is threaded (Task 8). The default must be a
    multi-column collapsing grid — the published form must not be single-column by default.

    Validates (bugfix): Requirement 2.2
    """
    page_css = render_page_styles({}).page_css
    tracks = _form_group_track_count(page_css)
    assert tracks is not None and tracks > 1, (
        f"MULTI_COLUMN (2.2): default form grid must be multi-column, got {tracks!r} tracks."
    )
    assert _grid_collapses_to_single_column(page_css), (
        "MULTI_COLUMN (2.2): the default form grid must collapse to a single column on small "
        "screens."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# LANDING_CSS_BYTE_IDENTICAL — Requirement 3.7 (the key Option-1 regression guard)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_landing_css_block_byte_identical_to_task3_snapshot():
    """Every landing-class rule is emitted byte-identical to the Task-3 baseline snapshot.

    Reuses the Task-3 fixture (``landing_classes_styling_bugfix_snapshot.json``) captured from the
    generator at the snapshot's fixed brand colours. Each landing rule must appear
    character-for-character in ``_build_page_css`` output and stay in its original order — the
    additive application-form block (Task 5.1) must not alter, reorder, or drop any landing rule
    so a future SAM landing page is unaffected (3.7).

    Validates (bugfix): Requirement 3.7
    """
    snap = _load(_LANDING_SNAPSHOT)
    page_css = _build_page_css(snap["color_primary"], snap["color_accent"])
    lines = _rule_lines(page_css)

    for rule in snap["landing_rules"]:
        assert rule in page_css, (
            "LANDING_CSS_BYTE_IDENTICAL (3.7): landing rule not emitted byte-identical after the "
            f"Task-5.1 form block was added: {rule!r}"
        )

    # Same order: the landing rules must be an ordered subsequence of the generated lines.
    it = iter(lines)
    assert all(any(rule == line for line in it) for rule in snap["landing_rules"]), (
        "LANDING_CSS_BYTE_IDENTICAL (3.7): the landing-class rules must stay in their original "
        "order in the generated page CSS (the form block is appended AFTER them, not interleaved)."
    )


def test_application_form_block_is_appended_after_landing_rules():
    """The new ``.application-form`` own-element rules are emitted AFTER the landing block.

    Confirms placement (DD-B1): the form heading/submit/focus/grid rules come after the last
    landing rule, so the additive block cannot perturb the landing-class ordering asserted above.

    Validates (bugfix): Requirement 3.7
    """
    snap = _load(_LANDING_SNAPSHOT)
    norm = _normalize(_build_page_css(snap["color_primary"], snap["color_accent"]))

    last_landing = norm.rfind("footer a {")
    first_form_own = norm.find('.application-form button[type="submit"]')
    assert last_landing != -1, "expected the footer landing rule to be present"
    assert first_form_own != -1, "expected the application-form submit rule to be present"
    assert first_form_own > last_landing, (
        "LANDING_CSS_BYTE_IDENTICAL (3.7): the application-form own-element rules must be appended "
        "AFTER the landing-class block, not interleaved with it."
    )
