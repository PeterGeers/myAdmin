"""
SAM half of the APPLIED-APPEARANCE parity pin across the two render paths (bugfix
``bugfix-published-form-styling`` Phase 5 / Task 20).

Two render paths are retained DELIBERATELY (design §E): the in-browser React preview
(immediate, no round-trip) and the published Python-rendered HTML. There is NO single
renderer and NO iframe. The fix is that BOTH derive the form's appearance from the SAME
resolved ``Look_And_Feel_Settings`` attributes + SAME defaults, and this parity pin asserts
the SAME APPLIED APPEARANCE on each path.

This file is the PUBLISHED-ARTIFACT half. Its frontend twin,
``frontend/.../__tests__/ApplicationFormPreview.appliedParity.test.tsx``, renders
``ApplicationFormPreview`` with the SAME attributes and asserts the preview applies the SAME
styling to the SAME logical elements. Both halves read ONE shared attribute fixture
(``applied_appearance_parity.json``), so they provably use the same input — a
``test_the_two_fixture_copies_are_byte_identical`` drift guard (below, mirrored on the
frontend) pins that the two fixture copies cannot diverge.

Why this is NOT the spec-15 task-13.2 string fixture
----------------------------------------------------
The spec-15 parity fixture (``page_styles_parity.json`` /
``test_page_styles_parity.py``) only pins that the two Layer-2 GENERATORS emit the same
``page_css`` / ``css_variables`` STRING. That is INSUFFICIENT and is part of this bug
(design "Grounded Root-Cause Investigation" §3 / design §E): the generator string can match
byte-for-byte while the published FORM is still unstyled, because the string themed only
landing-page classes the form markup never used. So this test asserts the APPLIED RESULT on
the published artifact — the brand colour reaches the form's OWN elements
(heading/submit/focus), the ``columns`` value produces a multi-column grid that collapses on
small screens, and the logo ``<img>`` + visible heading are rendered — NEVER merely that a
generator emits a string.

Applied-appearance predicates
-----------------------------
The applied-styling predicates mirror the now-passing Task-16.1 bug-condition test
(``test_published_form_applied_styling_bug_condition.py``) so the SAME notion of "applied"
is used on this (published) path as the bug-condition test already pins. This file keeps
them as a PARITY test driven from the SHARED fixture (not a Hypothesis exploration), so the
exact same attribute inputs flow to both paths.

In-memory fakes (no boto3, no AWS)
----------------------------------
Reuses the publish service's fake-seam shape (mirrors
``test_published_form_carries_styling_props.py`` /
``test_published_form_applied_styling_bug_condition.py``): a slug reader, a readiness
provider, a public-field-config reader with >=1 on-form field across two groups (so a
multi-column layout is observable), a look-and-feel reader returning the resolved VALUES, and
a capturing artifact writer (injecting it is what makes ``publish()`` a SUCCESSFUL publish).

Validates: Requirements 2.6; spec-15 Req 7.1 (admin preview reflects published)
"""

import json
import os
import re
import sys

import pytest

# repo root on sys.path (mirrors sam/conftest.py) so `sam.*` imports resolve.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_publish import ApplicationPublishService
from sam.members.domain.application_readiness import StaticMailReadinessProvider

_TENANT = "h-dcn"
_SLUG = "hdcn-application-form"
_PUBLIC_API_BASE = "https://api.jabaki.nl"


# ── the ONE shared attribute fixture + its frontend vendored twin ─────────────────────

_SAM_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "applied_appearance_parity.json",
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
    "applied_appearance_parity.json",
)

with open(_SAM_FIXTURE, encoding="utf-8") as _fh:
    _FIXTURE = json.load(_fh)

CASES = _FIXTURE["cases"]
_DEFAULT_PRIMARY = _FIXTURE["default_primary"]


# ── In-memory seams (no boto3, no AWS) ────────────────────────────────────────────────


class _FakeSlugReader:
    def get_form_slug(self, tenant_id):
        return _SLUG


class _FakeFieldConfigReader:
    """Fields across two groups so a multi-column layout is observable."""

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [
                {"key": "first_name", "type": "text", "functional_group": "personal"},
                {"key": "last_name", "type": "text", "functional_group": "personal"},
                {"key": "email", "type": "email", "functional_group": "contact"},
                {"key": "iban", "type": "text", "functional_group": "contact"},
            ],
            "functional_groups": [
                {"key": "personal", "label": {"nl": "Persoonlijk"}},
                {"key": "contact", "label": {"nl": "Contact"}},
            ],
            "locales": ["nl", "en"],
            "notice": {"version": None},
        }


class _FakeLookAndFeelReader:
    def __init__(self, values):
        self._values = dict(values)

    def get_look_and_feel(self, tenant_id):
        return self._values


class _CapturingArtifactWriter:
    def __init__(self):
        self.index_html = None
        self.form_json = None

    def publish_artifacts(self, slug, *, index_html, form_json):
        self.index_html = index_html
        self.form_json = form_json


def _publish(resolved_values):
    """Run a SUCCESSFUL publish; return the baked ``index.html`` string."""
    writer = _CapturingArtifactWriter()
    svc = ApplicationPublishService(
        slug_reader=_FakeSlugReader(),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
        field_config_reader=_FakeFieldConfigReader(),
        look_and_feel_reader=_FakeLookAndFeelReader(resolved_values),
        artifact_writer=writer,
    )
    result = svc.publish(_TENANT)
    assert result["success"] is True
    assert writer.index_html is not None
    return writer.index_html


# ── Applied-styling predicates (the form's OWN elements, NOT a generator string) ──────
#
# Mirror the Task-16.1 bug-condition test so the SAME notion of "applied" is used on the
# published path as the bug-condition test already pins.


def _normalize(html):
    return re.sub(r"\s+", " ", html).lower()


def _applies_brand_colour_to_form(html, color_primary):
    """(a) The brand colour reaches the form's OWN elements — heading/title, submit button,
    and input focus — inside a CSS rule targeting those elements (not merely present somewhere
    in the stylesheet / only on landing-page classes)."""
    norm = _normalize(html)
    colour = color_primary.lower()
    if colour not in norm:
        return False
    own_element_selectors = (
        ".application-form button",
        'button[type="submit"]',
        ".application-form h1",
        ".application-form h2",
        ".application-form .form-title",
        ".application-form input:focus",
        ".application-form select:focus",
        ".application-form textarea:focus",
        ".application-form :focus",
    )
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        selector, body = match.group(1), match.group(2)
        if colour in body and any(sel in selector for sel in own_element_selectors):
            return True
    return False


def _multi_column_grid_track_count(html):
    """Return the largest multi-column ``grid-template-columns`` track count declared for the
    form's own group/field container (>1), or 0 if none — so the parity test can compare the
    APPLIED column count the published path produced against the shared fixture's ``columns``."""
    norm = _normalize(html)
    form_container_selectors = (
        ".application-form .form-group",
        ".application-form .form-field",
        ".application-form .form-grid",
        ".application-form main",
        ".application-form",
    )
    best = 0
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        selector, body = match.group(1), match.group(2)
        if "grid-template-columns" not in body:
            continue
        if not any(sel in selector for sel in form_container_selectors):
            continue
        # Width-driven capped auto-fit: the COLUMN CAP is the calc() denominator in
        # minmax(max(16rem, calc((100% - ((N - 1) * gap)) / N)), 1fr).
        cap = re.search(r"max-width:\s*calc\(\s*(\d+)\s*\*\s*20rem", body)
        if cap:
            best = max(best, int(cap.group(1)))
            continue
        # Legacy fixed repeat(N, ...) literal.
        repeat_match = re.search(r"repeat\(\s*(\d+)", body)
        if repeat_match and int(repeat_match.group(1)) > 1:
            best = max(best, int(repeat_match.group(1)))
    return best


def _collapses_on_small_screens(html):
    """The form grid reflows to a single column on narrow screens.

    Width-driven: ``repeat(auto-fit, minmax(max(16rem, calc(...)), 1fr))`` inherently collapses to
    one column once the container is narrower than the 16rem floor — no media query. (A legacy
    ``@media ... 1fr`` collapse also counts.)
    """
    norm = _normalize(html)
    if re.search(r"auto-fit,\s*minmax\(\s*\d+(?:\.\d+)?(?:rem|px)", norm):
        return True
    return bool(
        re.search(
            r"@media[^{]*max-width[^{]*\{[^}]*(1fr|grid-template-columns:\s*none|"
            r"grid-template-columns:\s*1fr)",
            norm,
        )
    )


def _renders_logo(html, logo_ref):
    norm = _normalize(html)
    return bool(re.search(r"<img\b[^>]*src=", norm)) and logo_ref.lower() in norm


def _renders_heading(html, header_title):
    norm = _normalize(html)
    title_text = header_title.lower()
    for match in re.finditer(r"<(h1|h2|h3)\b[^>]*>(.*?)</\1>", norm):
        if title_text in match.group(2):
            return True
    for match in re.finditer(
        r'<div\b[^>]*class="[^"]*(title|header)[^"]*"[^>]*>(.*?)</div>', norm
    ):
        if title_text in match.group(2):
            return True
    return False


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """The publish render step resolves ``PUBLIC_API_BASE_URL`` fail-fast (no default)."""
    monkeypatch.setenv("PUBLIC_API_BASE_URL", _PUBLIC_API_BASE)


# ── Fixture / drift guards (both planes read the SAME attributes) ─────────────────────


def test_the_two_fixture_copies_are_byte_identical():
    """DRIFT GUARD: the canonical SAM fixture and the frontend vendored copy are byte-for-byte
    identical, so the published-artifact test and the preview test provably drive both render
    paths from the SAME resolved attributes (Req 2.6 / spec-15 Req 7.1). If either copy is
    edited without mirroring the other, this fails."""
    with open(_SAM_FIXTURE, "rb") as a, open(_FRONTEND_FIXTURE, "rb") as b:
        assert a.read() == b.read(), (
            "The canonical SAM applied-appearance parity fixture and its frontend vendored copy "
            "have drifted. Mirror the EXACT bytes to the other copy: "
            f"{_SAM_FIXTURE} <-> {_FRONTEND_FIXTURE}"
        )


def test_fixture_cases_carry_distinct_observable_values():
    """Guard the fixture is meaningful: every case supplies a brand colour that DIFFERS from the
    SAM default (so 'colour applied' is observable), a multi-column ``columns`` (>1), a logo
    reference, and a non-empty header_title."""
    assert CASES, "the shared fixture must carry at least one case"
    for case in CASES:
        values = case["input"]
        assert values["color_primary"].lower() != _DEFAULT_PRIMARY.lower(), (
            f"case {case['name']!r}: color_primary must differ from the SAM default so "
            f"'colour applied' is observable"
        )
        assert int(values["columns"]) > 1, (
            f"case {case['name']!r}: columns must be multi-column (>1) so the grid is observable"
        )
        assert values["logo"].strip(), f"case {case['name']!r}: logo must be non-empty"
        assert values["header_title"].strip(), (
            f"case {case['name']!r}: header_title must be non-empty"
        )


# ── The applied-appearance assertions on the PUBLISHED artifact ───────────────────────


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_published_artifact_applies_the_shared_fixture_attributes(case):
    """For the SAME resolved attributes the preview test uses, the PUBLISHED artifact applies
    the styling to the form's OWN logical elements: the brand colour on the form
    heading/submit/focus, a multi-column grid matching the fixture ``columns`` that collapses
    on small screens, the logo ``<img>``, and a visible heading. Asserts the APPLIED result on
    this path — never merely that a generator emits a string (Req 2.6 / spec-15 Req 7.1)."""
    values = case["input"]
    color_primary = values["color_primary"]
    columns = int(values["columns"])
    logo = values["logo"]
    header_title = values["header_title"]

    html = _publish(values)

    # (a) brand colour applied to the form's OWN elements (heading/submit/focus).
    assert _applies_brand_colour_to_form(html, color_primary), (
        f"case {case['name']!r}: brand colour {color_primary!r} is NOT applied to the "
        f"published form's own elements (heading/submit/focus)"
    )

    # (b) a multi-column grid matching the fixture `columns`, collapsing on small screens.
    applied_columns = _multi_column_grid_track_count(html)
    assert applied_columns == columns, (
        f"case {case['name']!r}: published form grid applies {applied_columns} columns, "
        f"expected the fixture's {columns}"
    )
    assert _collapses_on_small_screens(html), (
        f"case {case['name']!r}: published form grid does not collapse to a single column on "
        f"small screens"
    )

    # (c) the tenant logo <img> is rendered.
    assert _renders_logo(html, logo), (
        f"case {case['name']!r}: the logo {logo!r} is NOT rendered in the published body"
    )

    # (d) a visible heading carrying the header title is rendered.
    assert _renders_heading(html, header_title), (
        f"case {case['name']!r}: the header title {header_title!r} is NOT rendered as a visible "
        f"heading in the published body"
    )
