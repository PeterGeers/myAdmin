"""
Spec 14 Task 2.3 — OUTPUT PARITY of the shared rendering library against a committed fixture.

Tasks 2.1/2.2 proved the WIRING (``sam/tests/test_page_shell.py`` — the shell's contract +
dependency-free guarantee; ``sam/tests/test_application_form_render.py`` — that the SAM form
renders THROUGH ``page_shell`` with ``LandingPageStyles`` CSS). This file is the SEPARATE
PARITY pin (R7.2/R7.3): it freezes the ONE canonical document that the shared
``page_shell.render_page`` + the shared ``LandingPageStyles`` CSS source produce for a
representative published application-form page, and compares a fresh render BYTE-FOR-BYTE
against the committed golden fixture
``sam/tests/fixtures/application_form_page_shell_parity.html``.

Why a golden fixture (not just contains-checks): ``page_shell`` is a COPY-extraction of the
Flask landing shell scaffold (design D-RENDER) and ``LandingPageStyles`` is the SINGLE CSS
source both planes share. The golden documents the exact, stable output that single source
yields — so ANY accidental drift (a reordered ``<head>`` meta line, a changed ``<style>``
wrapper, an edited CSS rule or variable, a changed body scaffold) is caught by the
byte-exact assertion, not silently shipped. The render is driven by the REAL
``LandingPageStyles`` (steering 39 — prove against the real CSS source, never a hand-faked
CSS string), so the fixture genuinely pins the shared source's output.

Change-with-tests (steering 30/34): if ``page_shell``, the SAM wiring, or ``LandingPageStyles``
intentionally changes the output, REGENERATE this committed fixture in the SAME change (see
``_render_canonical_page`` below for the exact inputs) — do not weaken the assertion to pass.

Validates: Requirements R7.1 (shared shell + single CSS source), R7.2 (one canonical shared
output), R7.3 (shared as a pure-function library, not a runtime/store coupling)
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles (the single CSS source) lives in backend/src/services — resolved from
# backend/src on the path in dev/test (vendored into the Members layer at build time).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_form_render import render_application_form_page

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "application_form_page_shell_parity.html",
)


# ── the ONE canonical input (keep in lockstep with the committed golden fixture) ──────
# These are the exact inputs used to generate application_form_page_shell_parity.html.
# A representative page: SEO head meta, three authored groups (ordered), required text
# inputs, an email input, and an enum rendered as a <select> — enough that the fixture
# exercises the head-meta block, the real LandingPageStyles <style>, and the body scaffold.

_PUBLIC_FIELD_CONFIG = {
    "tenant_id": "h-dcn",
    "fields": [
        {
            "key": "first_name",
            "type": "text",
            "functional_group": "personal",
            "label": {"nl": "Voornaam", "en": "First name"},
            "required": True,
        },
        {
            "key": "last_name",
            "type": "text",
            "functional_group": "personal",
            "label": {"nl": "Achternaam", "en": "Last name"},
            "required": True,
        },
        {
            "key": "email",
            "type": "email",
            "functional_group": "contact",
            "label": {"nl": "E-mail", "en": "Email"},
            "required": True,
        },
        {
            "key": "membership_type",
            "type": "enum",
            "functional_group": "membership",
            "label": {"nl": "Lidmaatschap", "en": "Membership"},
            "options": [
                {"value": "junior", "label": {"nl": "Junior", "en": "Junior"}},
                {"value": "senior", "label": {"nl": "Senior", "en": "Senior"}},
            ],
        },
    ],
    "functional_groups": [
        {
            "key": "personal",
            "label": {"nl": "Persoonlijk", "en": "Personal"},
            "order": 10,
        },
        {"key": "contact", "label": {"nl": "Contact", "en": "Contact"}, "order": 20},
        {
            "key": "membership",
            "label": {"nl": "Lidmaatschap", "en": "Membership"},
            "order": 30,
        },
    ],
    "locales": ["nl", "en"],
    "notice": {"version": None},
}

_HEAD_META = {
    "title": "Aanmelden - Hondenschool DCN",
    "description": "Word lid van onze vereniging",
    "canonical": "https://h-dcn-aanmelden.jabaki.nl/",
    "og_image": "https://cdn.jabaki.nl/h-dcn/og.png",
    "site_name": "Hondenschool DCN",
}

_BRANDING = {
    "color_primary": "#2D5F8A",
    "color_accent": "#F4A261",
    "font_heading": "Inter",
    "font_body": "Inter",
    "base_spacing": "normal",
    "border_radius_global": "rounded",
    "shadow_style": "subtle",
}


def _render_canonical_page() -> str:
    """Render the ONE canonical page via the shared page_shell + real LandingPageStyles.

    To regenerate the golden fixture after an INTENTIONAL output change:
        python -c "from sam.tests.test_page_shell_parity import _render_canonical_page; \
                   open('sam/tests/fixtures/application_form_page_shell_parity.html','w',\
                   encoding='utf-8').write(_render_canonical_page())"
    (run with PYTHONPATH including the repo root and backend/src).
    """
    return render_application_form_page(
        _PUBLIC_FIELD_CONFIG,
        head_meta=_HEAD_META,
        branding=_BRANDING,
        locale="nl",
    )


def _read_fixture() -> str:
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        text = fh.read()
    # The generator writes the document with no trailing newline (it ends at </html>); a
    # committed file may pick up exactly one trailing newline. Normalize that single
    # trailing newline ONLY — any other whitespace difference is real drift and must fail.
    if text.endswith("\n") and not text.endswith("\n\n"):
        text = text[:-1]
    return text


def test_render_application_form_page_matches_committed_golden_fixture():
    """R7.2: the shared shell + single CSS source yield EXACTLY the committed canonical output.

    Byte-for-byte equality is the drift detector: a reordered head-meta line, an edited
    <style>/CSS rule, or a changed body scaffold all break this — forcing a deliberate,
    reviewed fixture regeneration rather than a silent output change.
    """
    rendered = _render_canonical_page()
    expected = _read_fixture()
    assert rendered == expected, (
        "Rendered page_shell/LandingPageStyles output DRIFTED from the committed golden "
        f"fixture ({_FIXTURE_PATH}). If this is an INTENTIONAL output change, regenerate the "
        "fixture in THIS change (see _render_canonical_page's docstring); do NOT weaken this "
        "assertion."
    )


def test_golden_fixture_pins_the_shared_page_shell_scaffold():
    """R7.1/R7.3: the golden is a real page_shell document — not a hand-authored HTML blob.

    These structural anchors prove the fixture is the shared SHELL's output (the scaffold
    page_shell owns), so the byte-exact test above is pinning the right thing. Faithful to the
    Flask reference shell's scaffold (same <head> meta block, single <style>, <body> wrapper).
    """
    expected = _read_fixture()
    assert expected.startswith('<!DOCTYPE html>\n<html lang="nl">')
    assert expected.rstrip().endswith("</html>")
    # The page_shell head-meta scaffold (SEO/OG/Twitter/canonical), in the shared order:
    assert "<title>Aanmelden - Hondenschool DCN</title>" in expected
    assert '<meta property="og:locale" content="nl_NL" />' in expected
    assert '<meta name="twitter:card" content="summary_large_image" />' in expected
    assert (
        '<link rel="canonical" href="https://h-dcn-aanmelden.jabaki.nl/" />' in expected
    )
    # Exactly one <style> block wraps the single CSS source's output:
    assert expected.count("<style>") == 1 and expected.count("</style>") == 1
    # The body scaffold composed by the SAM wiring:
    assert '<form class="application-form" method="post">' in expected


def test_golden_fixture_pins_the_single_landing_page_styles_css_source():
    """R7.2: the golden embeds the REAL LandingPageStyles output (one CSS source of truth).

    Assert the fixture carries the exact CSS the single source produces for the canonical
    branding — the :root variable block and the colour-threaded page CSS — so a change to
    LandingPageStyles is caught here too, not just an incidental scaffold edit. Proved against
    the real generator (steering 39), never a hand-faked CSS string.
    """
    from services.landing_page_styles import LandingPageStyles

    expected = _read_fixture()
    css_variables = LandingPageStyles.build_css_variables(_BRANDING)
    page_css = LandingPageStyles.build_page_css(
        _BRANDING["color_primary"], _BRANDING["color_accent"]
    )
    # The committed fixture embeds the SINGLE source's CSS verbatim inside the <style> block.
    assert css_variables in expected, (
        "fixture lost the LandingPageStyles :root variable block"
    )
    assert page_css in expected, "fixture lost the LandingPageStyles page CSS"
    # And the primary/accent colours are actually threaded (not a stale hard-coded palette):
    assert "color: #2D5F8A;" in expected
    assert "background: #F4A261;" in expected
