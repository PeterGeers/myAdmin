"""
SAM bug-condition EXPLORATION test — the PUBLISHED application form does NOT apply the
tenant's look-and-feel to the form's OWN elements (bugfix ``bugfix-published-form-styling``
Task 1 / Property 1: Bug Condition).

Feature: bugfix-published-form-styling. This is Phase-0 "Reproduce (A)": it asserts the
PRODUCED / baked ``index.html`` artifact genuinely APPLIES the styling, and is EXPECTED TO
FAIL on the current (unfixed) code — that failure confirms the bug and closes the
"false-parity" gap that hid it.

Why this test exists (the false-parity gap it closes)
-----------------------------------------------------
The shipped spec-15 test ``test_published_form_carries_styling_props.py`` asserts only that
the Layer-2 generator's ``page_css`` STRING is present in the artifact
(``expected.page_css in writer.index_html``). That string is present — yet the form is still
unstyled, because the Layer-2 CSS targets LANDING-PAGE classes (``.hero`` / ``.cta`` /
``.btn`` / ``.pricing-card`` / the gallery/faq grids) the application-form markup never uses,
and the brand colours are inlined ONLY into those landing rules (design "Grounded Root-Cause
Investigation" §1). So "the generator emits a string" ≠ "the form is styled".

This test instead asserts the APPLIED result on the form's OWN elements (design Property 1 /
Bug Details root cause 1-2):

  (a) the brand colour reaches the form's own elements — the form heading/title, the submit
      ``<button type="submit">``, and the input/select/textarea ``:focus`` state;
  (b) the field groups are laid out in a MULTI-COLUMN grid that COLLAPSES to a single column
      on small screens;
  (c) the tenant LOGO ``<img>`` is rendered in the body;
  (d) a visible TITLE / heading element is rendered in the body (NOT merely the non-visible
      ``<title>`` browser-tab element).

Expected outcome on UNFIXED code: FAILS — the current ``.application-form`` CSS only sets
field margins, grey ``#ccc`` input borders and error reds (no brand colour, no grid), and the
renderer emits no logo ``<img>`` and no body heading. DO NOT fix the test or the product code
here; this test encodes the expected behaviour and will PASS once the fix (Phases 1-2) lands
(re-run as Task 16.1).

Scoped-PBT approach (design "Exploratory Bug Condition Checking")
----------------------------------------------------------------
Scoped to concrete distinct-value cases for reproducibility: a vivid ``color_primary`` that
differs from the SAM default, ``columns=3``, a ``logo`` reference, and a ``header_title``. A
Hypothesis strategy (>=100 iterations) draws those distinct values over a constrained space so
the counterexample is reproducible rather than a single hand-picked example. After Phase 2 all
four are SUPPORTED attributes end-to-end (``columns`` / ``logo`` / ``header_title`` became
supported in Task 8), so all four drawn values are fed to the publish path and the test now
exercises the FIXED end-to-end contract. When this test was first written (Task 1, Phase 0),
those three were not yet carried end-to-end, so only ``color_primary`` could be fed — that gap
WAS the bug, now closed.

In-memory fakes (no boto3, no AWS)
----------------------------------
Reuses the publish service's fake-seam shape (mirrors
``test_published_form_carries_styling_props.py``): a slug reader, a readiness provider, a
public-field-config reader with >=1 on-form field, a look-and-feel reader returning the
resolved VALUES, and a capturing artifact writer. Injecting the writer is what makes
``publish()`` a SUCCESSFUL publish (an artifact IS written), so the baked artifact is the
thing the bug condition is asserted over.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.6
"""

import os
import re
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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

# The SAM-owned default primary colour (sam/shared/page_styles._DEFAULTS["color_primary"]).
# A distinct brand colour must differ from this so "colour applied" is observable.
_DEFAULT_COLOR_PRIMARY = "#2D5F8A"


# ── In-memory seams (no boto3, no AWS) ────────────────────────────────────────────────


class _FakeSlugReader:
    def get_form_slug(self, tenant_id):
        return _SLUG


class _FakeFieldConfigReader:
    """One on-form field across two groups so a multi-column layout is observable."""

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
    """In-memory ``LookAndFeelSettingsReader`` — returns the resolved VALUES.

    All four authored attributes are now supported end-to-end (``color_primary`` plus the
    Phase-2 extension ``columns`` / ``logo`` / ``header_title`` — Task 8), so every value drawn
    by the strategy is fed to the publish path. ``render_page_styles`` accepts the ten-attribute
    set and ``columns`` drives the grid; the renderer (Task 6) consumes ``logo`` / ``header_title``
    to emit the logo ``<img>`` and the visible heading. Publish therefore SUCCEEDS and the baked
    artifact carries the APPLIED styling asserted below — the fixed end-to-end contract.
    """

    def __init__(self, values):
        self._values = dict(values)

    def get_look_and_feel(self, tenant_id):
        return self._values


class _CapturingArtifactWriter:
    """Captures the published ``index_html`` — injecting it makes publish() SUCCESSFUL."""

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


# ── Applied-styling assertions (the form's OWN elements, NOT a generator string) ──────


def _normalize(html):
    """Lower-case + collapse whitespace so CSS/attribute matching is layout-insensitive."""
    return re.sub(r"\s+", " ", html).lower()


def _applies_brand_colour_to_form(html, color_primary):
    """(a) The brand colour reaches the form's OWN elements — heading/title, submit button,
    and input focus — not only the landing-page classes.

    A CSS rule that both targets an ``.application-form`` own element (the submit button,
    the form heading, or the input ``:focus`` state) AND carries the brand colour.
    """
    norm = _normalize(html)
    colour = color_primary.lower()
    if colour not in norm:
        return False
    # Find CSS rule blocks that target the form's own elements and check the brand colour
    # appears inside one of them (applied), not merely somewhere in the stylesheet.
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


def _has_collapsing_multi_column_grid(html):
    """(b) The field groups are laid out in a MULTI-COLUMN grid that COLLAPSES to a single
    column on small screens.

    Requires a grid rule on the form's own group/field container with more than one column,
    plus a small-screen media query that collapses it to a single column.
    """
    norm = _normalize(html)
    form_container_selectors = (
        ".application-form .form-group",
        ".application-form .form-field",
        ".application-form .form-grid",
        ".application-form main",
        ".application-form",
    )
    has_multi_col = False
    has_collapse = False
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", norm):
        selector, body = match.group(1), match.group(2)
        if "grid-template-columns" not in body:
            continue
        if not any(sel in selector for sel in form_container_selectors):
            continue
        # Width-driven capped auto-fit: multi-column-CAPABLE iff the calc() cap denominator is >1,
        # and it INHERENTLY reflows to one column (auto-fit + a rem/px floor) with no breakpoint.
        cap = re.search(r"max-width:\s*calc\(\s*(\d+)\s*\*\s*20rem", body)
        if "auto-fit" in body and re.search(r"minmax\(\s*\d+(?:\.\d+)?(?:rem|px)", body):
            has_collapse = True
            if cap and int(cap.group(1)) > 1:
                has_multi_col = True
        # Legacy fixed repeat(N>1, ...) multi-column.
        repeat_match = re.search(r"repeat\(\s*(\d+)", body)
        if repeat_match and int(repeat_match.group(1)) > 1:
            has_multi_col = True
    # Legacy media-query collapse (back-compat).
    if not has_collapse:
        has_collapse = bool(
            re.search(
                r"@media[^{]*max-width[^{]*\{[^}]*(1fr|grid-template-columns:\s*none|"
                r"grid-template-columns:\s*1fr)",
                norm,
            )
        )
    return has_multi_col and has_collapse


def _renders_logo(html, logo_ref):
    """(c) The tenant logo ``<img>`` is rendered in the body."""
    norm = _normalize(html)
    return bool(re.search(r"<img\b[^>]*src=", norm)) and logo_ref.lower() in norm


def _renders_heading(html, header_title):
    """(d) A VISIBLE title/heading element is in the body (not just the <title> tab element)."""
    norm = _normalize(html)
    title_text = header_title.lower()
    # A visible heading element carrying the authored title text (h1/h2/h3 or a titled div),
    # NOT the non-visible <title>...</title> browser-tab element.
    for match in re.finditer(r"<(h1|h2|h3)\b[^>]*>(.*?)</\1>", norm):
        if title_text in match.group(2):
            return True
    for match in re.finditer(
        r'<div\b[^>]*class="[^"]*(title|header)[^"]*"[^>]*>(.*?)</div>', norm
    ):
        if title_text in match.group(2):
            return True
    return False


# ── Scoped strategy: concrete DISTINCT values (reproducible counterexamples) ──────────

# Vivid brand colours that DIFFER from the SAM default primary (so "applied" is observable).
_DISTINCT_PRIMARIES = [
    "#C01030",
    "#7B2CBF",
    "#0A7E3F",
    "#D62828",
    "#1D3557",
    "#E63946",
]
_LOGO_REFS = [
    "https://cdn.jabaki.nl/h-dcn/logo.png",
    "https://assets.example.org/brand/mark.svg",
    "https://cdn.jabaki.nl/tenant/emblem.webp",
]
_HEADER_TITLES = [
    "Word lid van DCN",
    "Aanmelden ledenadministratie",
    "Inschrijfformulier 2026",
]
_COLUMNS = [2, 3]


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """The publish render step resolves ``PUBLIC_API_BASE_URL`` fail-fast (no default)."""
    monkeypatch.setenv("PUBLIC_API_BASE_URL", _PUBLIC_API_BASE)


@settings(max_examples=120, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    color_primary=st.sampled_from(_DISTINCT_PRIMARIES),
    logo=st.sampled_from(_LOGO_REFS),
    header_title=st.sampled_from(_HEADER_TITLES),
    columns=st.sampled_from(_COLUMNS),
)
def test_published_form_does_not_apply_look_and_feel_to_its_own_elements(
    color_primary, logo, header_title, columns
):
    """Property 1 (Bug Condition): for a tenant whose resolved look-and-feel carries distinct
    values (a vivid brand colour, a logo, a header title, a multi-column choice), the published
    artifact SHALL apply that styling to the form's OWN elements — brand colour on the form
    heading/submit/focus, a collapsing multi-column grid, the logo, and a visible heading.

    EXPECTED ON UNFIXED CODE: FAILS. The current artifact themes only landing-page classes,
    lays the form out single-column at all widths, and renders neither logo nor heading. Each
    assertion names the counterexample so the failing example is self-describing.

    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.6
    """
    assert color_primary.lower() != _DEFAULT_COLOR_PRIMARY.lower()

    # All four authored values are now fed to the publish path. After Phase 2 (Task 8 made
    # `columns` / `logo` / `header_title` SUPPORTED attributes end-to-end; Task 6 renders the
    # logo + heading; Task 10 validates them), the publish/Layer-2 path CAN carry all four, so
    # the test exercises the FIXED end-to-end contract: the brand colour themes the form's own
    # elements, `columns` drives the collapsing grid, and the logo + header title are rendered.
    html = _publish(
        {
            "color_primary": color_primary,
            "logo": logo,
            "header_title": header_title,
            "columns": columns,
        }
    )

    # (a) brand colour applied to the form's OWN elements (heading/submit/focus) — Req 1.1/2.1.
    assert _applies_brand_colour_to_form(html, color_primary), (
        f"brand colour {color_primary!r} is NOT applied to the form's own elements "
        f"(heading/submit/focus) — it only themes landing-page classes (bug 1.1)"
    )

    # (b) multi-column grid collapsing on small screens — Req 1.2/2.2.
    assert _has_collapsing_multi_column_grid(html), (
        f"no multi-column collapsing grid for the form groups (columns={columns}); "
        f"the form stacks single-column at every width (bug 1.2)"
    )

    # (c) the tenant logo <img> is rendered — Req 1.3/2.3.
    assert _renders_logo(html, logo), (
        f"the tenant logo {logo!r} is NOT rendered in the published body (bug 1.3)"
    )

    # (d) a visible heading/title element is rendered — Req 1.4/2.4.
    assert _renders_heading(html, header_title), (
        f"the header title {header_title!r} is NOT rendered as a visible heading in the "
        f"body (only a non-visible <title> tab element exists) (bug 1.4)"
    )
