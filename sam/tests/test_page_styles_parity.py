"""
spec 15 (SAM Page Look-and-Feel) task 13.2 — the SAM/PYTHON half of the Layer-2/3
PYTHON ↔ REACT parity PIN.

Task 13.1 made ``frontend/.../pageStyles.ts`` (``renderPageStyles``) a byte-level mirror of
the SAM-owned AUTHORITATIVE Python Layer-2 generator ``sam.shared.page_styles.render_page_styles``.
This file FORMALIZES that parity as a COMMITTED shared fixture both planes read (DD-3 /
design §C5, Req 7.1 / 7.3), mirroring the existing ``buildPreviewConfig`` ↔
``get_public_field_config`` pin (``test_application_filter_parity.py``):

  the SAME canonical fixture cases, fed to the REAL Python generator
  (:func:`render_page_styles`), must reproduce the SAME ``expected``
  cssVariables / pageCss / fontLinks the frontend vitest parity test
  (``pageStyles.parity.test.ts``) asserts ``renderPageStyles`` produces.

The ONE canonical fixture lives at ``sam/tests/fixtures/page_styles_parity.json``; the
frontend test root carries a byte-identical vendored copy. The ``expected`` values were
GENERATED FROM this Python generator (via
``.agent-output/gen_page_styles_parity_fixture.py``) so they are authoritative — a drift in
EITHER the Python generator or the TS mirror is caught on BOTH sides.

``test_the_two_fixture_copies_are_byte_identical`` is the DRIFT GUARD: if either copy is
edited without mirroring the other, it fails — so "both planes compare against the SAME
expected output" is enforced, not merely asserted by convention.

The Python generator is the AUTHORITY: if the two ever diverge the CLIENT (``pageStyles.ts``)
is reconciled to the Python output, never this assertion weakened. If the Python output
changes intentionally, REGENERATE the fixture in the SAME change (see :func:`build_fixture`
below — ``python -c "from sam.tests.test_page_styles_parity import write_fixtures; \
write_fixtures()"`` run with PYTHONPATH including the repo root) and the drift guard then
forces the frontend copy to be mirrored byte-for-byte; do NOT weaken either plane's assertion.

Validates: Requirements 7.1, 7.3
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.shared.page_styles import render_page_styles

# ── the ONE canonical fixture + its frontend vendored twin ────────────────────────────

_SAM_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "page_styles_parity.json",
)
_FRONTEND_FIXTURE = os.path.join(
    _REPO_ROOT,
    "frontend",
    "src",
    "components",
    "TenantAdmin",
    "MembersConfig",
    "__tests__",
    "fixtures",
    "page_styles_parity.json",
)

with open(_SAM_FIXTURE, encoding="utf-8") as _fh:
    FIXTURE = json.load(_fh)

CASES = FIXTURE["cases"]


# ── the canonical case DEFINITIONS (the single source the committed fixture is built from) ──
# (name, description, input settings). Covers the case classes task 13.2 mandates:
# all-defaults (empty), the full seven custom values, several partial subsets, and a
# sanitiser exercise. The committed ``expected`` for each is GENERATED from the Python
# generator (see build_fixture / write_fixtures) so it is authoritative.
_CASE_DEFS = [
    (
        "all_defaults_empty",
        "All-defaults: empty settings -> every attribute resolves to its SAM-owned default "
        "(system fonts, professional colours, normal/rounded/subtle).",
        {},
    ),
    (
        "full_seven_custom",
        "Full seven custom values: every supported attribute supplied a distinct non-default "
        "value, with web fonts so font_links are emitted.",
        {
            "color_primary": "#112233",
            "color_accent": "#ffeedd",
            "font_heading": "Inter",
            "font_body": "Lora",
            "base_spacing": "relaxed",
            "border_radius_global": "pill",
            "shadow_style": "dramatic",
        },
    ),
    (
        "partial_colours_only",
        "Partial subset: only the two brand colours supplied; the other five fall back to "
        "defaults.",
        {
            "color_primary": "#2D5F8A",
            "color_accent": "#F4A261",
        },
    ),
    (
        "partial_fonts_mixed",
        "Partial subset: a web heading font + a system body font (two fonts, one web one "
        "system) with a compact/sharp enum mix; colours + shadow default.",
        {
            "font_heading": "Open Sans",
            "font_body": "system",
            "base_spacing": "compact",
            "border_radius_global": "sharp",
        },
    ),
    (
        "partial_enums_only",
        "Partial subset: only the three enum attributes supplied (no colours, no fonts); "
        "fonts + colours default.",
        {
            "base_spacing": "normal",
            "border_radius_global": "rounded",
            "shadow_style": "medium",
        },
    ),
    (
        "sanitiser_dangerous_values",
        "Sanitiser exercise: a brand colour carrying url(...) and a font family carrying "
        "expression(...)/javascript: — all dangerous patterns stripped before reaching CSS.",
        {
            "color_primary": "url(evil.css)#2D5F8A",
            "color_accent": "javascript:alert(1)#F4A261",
            "font_heading": "expression(x)Evil",
            "font_body": "Inter",
            "base_spacing": "normal",
            "border_radius_global": "rounded",
            "shadow_style": "subtle",
        },
    ),
]

_FIXTURE_COMMENT = [
    "SHARED, CANONICAL parity fixture for spec 15 (SAM Page Look-and-Feel), task 13.2.",
    "It pins the React/TS Layer-2 generator (renderPageStyles, pageStyles.ts) to the",
    "SAM-owned AUTHORITATIVE Python Layer-2 generator (render_page_styles,",
    "sam/shared/page_styles/__init__.py) so a drift in EITHER implementation is caught on",
    "BOTH planes (DD-3 / design C5, Req 7.1 / 7.3).",
    "",
    "The `expected` cssVariables/pageCss/fontLinks were GENERATED FROM the Python generator",
    "and are therefore authoritative. ONE file is canonical:",
    "sam/tests/fixtures/page_styles_parity.json. The frontend test root carries a",
    "byte-identical vendored copy at",
    "frontend/src/components/TenantAdmin/MembersConfig/__tests__/fixtures/page_styles_parity.json;",
    "a guard test on EACH plane asserts the two copies are byte-for-byte identical.",
    "",
    "Each plane feeds every case's `input` to its REAL generator and asserts the produced",
    "cssVariables/pageCss/fontLinks equal the case's `expected` block below.",
    "",
    "Change-with-tests: if the Python generator intentionally changes output, REGENERATE",
    "this fixture in the SAME change (sam.tests.test_page_styles_parity.write_fixtures) and",
    "mirror the EXACT bytes to the frontend copy; do NOT weaken either plane's assertion to",
    "go green.",
]


def build_fixture() -> dict:
    """Build the canonical fixture dict by running the AUTHORITATIVE Python generator over
    :data:`_CASE_DEFS`. The committed JSON is the serialization of exactly this."""
    cases = []
    for name, description, settings in _CASE_DEFS:
        styles = render_page_styles(settings)
        cases.append(
            {
                "name": name,
                "description": description,
                "input": settings,
                "expected": {
                    "cssVariables": styles.css_variables,
                    "pageCss": styles.page_css,
                    "fontLinks": styles.font_links,
                },
            }
        )
    return {"$comment": _FIXTURE_COMMENT, "cases": cases}


def _serialize_fixture() -> str:
    """The exact byte content of the committed fixture (indent=2, ASCII, trailing newline)."""
    return json.dumps(build_fixture(), indent=2, ensure_ascii=True) + "\n"


def write_fixtures() -> None:
    """Regenerate BOTH the canonical SAM fixture and the byte-identical frontend copy.

    Run after an INTENTIONAL Python-generator output change:
        python -c "from sam.tests.test_page_styles_parity import write_fixtures; write_fixtures()"
    (with PYTHONPATH including the repo root).
    """
    content = _serialize_fixture()
    for path in (_SAM_FIXTURE, _FRONTEND_FIXTURE):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def test_the_two_fixture_copies_are_byte_identical():
    """DRIFT GUARD: the canonical SAM fixture and the frontend vendored copy are byte-for-byte
    identical, so both planes provably compare against the SAME ``expected`` output (Req 7.3)."""
    with open(_SAM_FIXTURE, "rb") as a, open(_FRONTEND_FIXTURE, "rb") as b:
        assert a.read() == b.read(), (
            "The canonical SAM page-styles parity fixture and its frontend vendored copy have "
            "drifted. Regenerate the fixture and mirror the EXACT bytes to the other copy: "
            f"{_SAM_FIXTURE} <-> {_FRONTEND_FIXTURE}"
        )


def test_committed_fixture_matches_the_freshly_built_serialization():
    """The committed fixture equals what :func:`build_fixture` produces NOW — so the fixture
    can never silently go stale relative to the generator / case definitions. If this fails
    after an intentional generator change, run ``write_fixtures()`` to regenerate both copies."""
    with open(_SAM_FIXTURE, encoding="utf-8") as fh:
        committed = fh.read()
    assert committed == _serialize_fixture(), (
        "The committed page-styles parity fixture is stale vs. the Python generator. Regenerate "
        "it in THIS change: python -c \"from sam.tests.test_page_styles_parity import "
        "write_fixtures; write_fixtures()\" (PYTHONPATH=repo root); do NOT hand-edit expected values."
    )


def test_fixture_covers_the_required_case_classes():
    """The shared fixture covers the case classes task 13.2 mandates: all-defaults (empty),
    the full seven custom values, several partial subsets, and a sanitiser exercise."""
    names = {c["name"] for c in CASES}
    # all-defaults (empty input)
    assert "all_defaults_empty" in names
    assert next(c for c in CASES if c["name"] == "all_defaults_empty")["input"] == {}
    # full seven custom values
    full = next(c for c in CASES if c["name"] == "full_seven_custom")["input"]
    assert set(full) == {
        "color_primary",
        "color_accent",
        "font_heading",
        "font_body",
        "base_spacing",
        "border_radius_global",
        "shadow_style",
    }
    # several partial subsets
    partials = [n for n in names if n.startswith("partial_")]
    assert len(partials) >= 2
    # at least one value exercising the sanitiser
    assert "sanitiser_dangerous_values" in names


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_generator_reproduces_the_canonical_expected(case):
    """The REAL Python generator, fed each canonical case's input, produces the SAME
    cssVariables / pageCss / fontLinks the frontend parity test pins ``renderPageStyles`` to
    (Req 7.1 / 7.3). The Python output is the AUTHORITY the shared ``expected`` was generated from."""
    styles = render_page_styles(case["input"])
    expected = case["expected"]
    assert styles.css_variables == expected["cssVariables"], (
        f"case {case['name']!r}: cssVariables drifted from the canonical fixture"
    )
    assert styles.page_css == expected["pageCss"], (
        f"case {case['name']!r}: pageCss drifted from the canonical fixture"
    )
    assert styles.font_links == expected["fontLinks"], (
        f"case {case['name']!r}: fontLinks drifted from the canonical fixture"
    )


def test_sanitiser_case_actually_strips_dangerous_patterns():
    """Guard the sanitiser case is meaningful: its INPUT carries dangerous CSS patterns but the
    pinned ``expected`` output has them stripped (so the fixture genuinely exercises the sanitiser)."""
    case = next(c for c in CASES if c["name"] == "sanitiser_dangerous_values")
    raw_values = " ".join(str(v) for v in case["input"].values())
    assert "url(" in raw_values or "javascript:" in raw_values or "expression(" in raw_values
    out = case["expected"]["cssVariables"] + case["expected"]["pageCss"]
    assert "url(" not in out
    assert "javascript:" not in out
    assert "expression(" not in out
