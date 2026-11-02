"""
Spec 14 Task 2.2 — SAM application-form SHELL RENDERER tests (design §C2/C3 / R7).

Pins the observable contract of
:func:`sam.members.domain.application_form_render.render_application_form_page` — the SAM
plane's wiring of the shared, plane-neutral page shell: it composes the applicant body from
the public field config, produces the CSS from ``LandingPageStyles`` (the SINGLE CSS source),
and hands head_meta + body + css to :func:`sam.shared.page_shell.render_page` (the shared
shell owns the scaffold). "Share the mechanism, not the store" (R7.3): this is a library call,
never a cross-plane runtime call.

Output PARITY against a real Flask-shell fixture is the SEPARATE task 2.3 — this file pins the
WIRING: that the SAM form renders its shell THROUGH page_shell (R7.1), that the applicant body
is built only from the whitelisted public schema, and that config values are XSS-escaped.

Validates: Requirements R7.1 (SAM form renders its shell via page_shell), R7.3 (shared as a
library), R5.2 (only application-visible whitelisted fields reach the body)
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles lives in backend/src/services (vendored into the Members layer at build);
# the dev/test run resolves it from backend/src on the path.
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_form_render import (
    build_form_body_html,
    render_application_form_page,
)


def _config(fields=None, groups=None):
    """A minimal get_public_field_config-shaped dict (the single-filter-authority output)."""
    return {
        "tenant_id": "h-dcn",
        "fields": fields if fields is not None else [],
        "functional_groups": groups if groups is not None else [],
        "locales": ["nl", "en"],
        "notice": {"version": None},
    }


def test_render_returns_full_document_composed_via_page_shell():
    """R7.1: the SAM form renders its shell THROUGH the shared page_shell scaffold."""
    cfg = _config(fields=[{"key": "email", "type": "email", "label": {"nl": "E-mail"}}])
    out = render_application_form_page(
        cfg, head_meta={"title": "Aanmelden", "canonical": "https://h-dcn-x.jabaki.nl/"}
    )
    # page_shell owns these scaffold markers:
    assert out.startswith("<!DOCTYPE html>")
    for marker in ("<head>", "<style>", "<body>", "</html>"):
        assert marker in out
    # head_meta flowed through the shared shell:
    assert "<title>Aanmelden</title>" in out
    assert 'href="https://h-dcn-x.jabaki.nl/"' in out
    # the SAM-composed applicant body:
    assert 'class="application-form"' in out
    assert 'name="email"' in out
    assert 'type="email"' in out


def test_css_comes_from_landing_page_styles_single_source():
    """R7.1: CSS is produced by LandingPageStyles (the ONE source) and lands in the <style>."""
    out = render_application_form_page(
        _config(fields=[{"key": "name"}]),
        head_meta={"title": "x"},
        branding={"color_primary": "#123456", "color_accent": "#abcdef"},
    )
    # LandingPageStyles.build_css_variables emits a :root block; build_page_css uses the colours.
    assert ":root {" in out
    assert "#123456" in out  # the primary colour threaded into the single CSS source


def test_body_renders_only_whitelisted_fields_from_the_public_schema():
    """R5.2: the body is built ONLY from the public (already-filtered) field list."""
    cfg = _config(
        fields=[
            {"key": "first_name", "label": {"nl": "Voornaam"}},
            {"key": "last_name", "label": {"nl": "Achternaam"}},
        ]
    )
    body = build_form_body_html(cfg)
    assert 'name="first_name"' in body
    assert 'name="last_name"' in body
    # nothing else — a field the tenant did not expose simply is not in the config, so cannot leak
    assert body.count('class="form-field"') == 2


def test_required_flag_from_public_schema_marks_the_control_required():
    """R4b.6: the application-requiredness from the public schema drives the `required` attr."""
    body = build_form_body_html(
        _config(fields=[{"key": "email", "type": "email", "required": True}])
    )
    assert "required" in body


def test_choices_render_as_a_select_with_escaped_options():
    """A field carrying canonical `options` renders a <select>; option values/labels are escaped."""
    body = build_form_body_html(
        _config(
            fields=[
                {
                    "key": "membership",
                    "options": [
                        {"value": "junior", "label": {"nl": "Junior"}},
                        {"value": "senior", "label": {"nl": "Senior"}},
                    ],
                }
            ]
        )
    )
    assert "<select" in body
    assert '<option value="junior">Junior</option>' in body
    assert '<option value="senior">Senior</option>' in body


def test_config_values_are_html_escaped_no_stored_xss_in_the_body():
    """Config-sourced values are escaped before entering markup (XSS-safe body composition)."""
    body = build_form_body_html(
        _config(fields=[{"key": "note", "label": {"nl": "<script>alert(1)</script>"}}])
    )
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_fields_are_grouped_and_ordered_by_the_authored_group_catalog():
    """spec 13 R2: sections order by the authored functional_groups catalog; heading = label."""
    cfg = _config(
        fields=[
            {"key": "email", "functional_group": "contact", "label": {"nl": "E-mail"}},
            {
                "key": "first_name",
                "functional_group": "personal",
                "label": {"nl": "Voornaam"},
            },
        ],
        groups=[
            {"key": "personal", "label": {"nl": "Persoonlijk"}, "order": 10},
            {"key": "contact", "label": {"nl": "Contact"}, "order": 20},
        ],
    )
    body = build_form_body_html(cfg)
    # personal (order 10) section must precede contact (order 20)
    assert body.index("Persoonlijk") < body.index("Contact")
    assert body.index('name="first_name"') < body.index('name="email"')


def test_empty_form_renders_a_valid_shell_without_fields():
    """An empty (no-field) config still renders a valid document shell (defensive)."""
    out = render_application_form_page(_config(), head_meta={"title": "x"})
    assert out.startswith("<!DOCTYPE html>")
    assert 'class="application-form"' in out
    assert 'class="form-field"' not in out
