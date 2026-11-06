"""
Spec 14 Task 2.2 — SAM application-form SHELL RENDERER tests (design §C2/C3 / R7).

Pins the observable contract of
:func:`sam.members.domain.application_form_render.render_application_form_page` — the SAM
plane's wiring of the shared, plane-neutral page shell: it composes the applicant body from
the public field config, produces the CSS from the SAM-owned Layer-2 generator
``sam.shared.page_styles.render_page_styles`` (the SINGLE, SAM-owned CSS source — spec 15 /
DD-1, task 7.2 cut it over from the former Flask ``LandingPageStyles`` import), and hands
head_meta + body + css to :func:`sam.shared.page_shell.render_page` (the shared shell owns the
scaffold). "Share the mechanism, not the store" (R7.3): this is a library call, never a
cross-plane runtime call.

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


def test_css_comes_from_sam_owned_page_styles_single_source():
    """R7.1 / spec 15 §C4 (task 7.2): CSS is produced by the SAM-owned Layer-2 generator
    (`sam.shared.page_styles.render_page_styles`) — now the ONE CSS source — and lands in the
    <style>. This is the cutover from the former Flask `LandingPageStyles` import on the render
    path (spec 15 / DD-1): styling is produced entirely from SAM-owned code (Req 3.5).
    """
    out = render_application_form_page(
        _config(fields=[{"key": "name"}]),
        head_meta={"title": "x"},
        branding={"color_primary": "#123456", "color_accent": "#abcdef"},
    )
    # render_page_styles emits a :root variables block (css_variables); the page CSS threads the
    # primary colour — both land verbatim inside the single <style> block page_shell wraps.
    assert ":root {" in out
    assert "#123456" in out  # the primary colour threaded into the SAM-owned CSS source


def test_render_uses_sam_owned_generator_not_flask_landing_page_styles(monkeypatch):
    """spec 15 / DD-1 (task 7.2): the render path calls the SAM-owned `render_page_styles`, NOT
    the Flask `services.landing_page_styles.LandingPageStyles`. Patch the SAM generator to a
    sentinel and assert its output is what reaches the <style> — proving the cutover is wired to
    the SAM-owned source (no runtime read of the Flask plane, Req 2.2/3.5).
    """
    import sam.members.domain.application_form_render as render_mod
    from sam.shared.page_styles import PageStyles

    sentinel = PageStyles(
        css_variables=":root { --sam-owned-sentinel: 1; }",
        page_css=".sam-owned-sentinel { color: #abc; }",
        font_links="",
    )
    monkeypatch.setattr(render_mod, "render_page_styles", lambda settings: sentinel)
    out = render_application_form_page(
        _config(fields=[{"key": "name"}]),
        head_meta={"title": "x"},
        branding={"color_primary": "#123456"},
    )
    assert "--sam-owned-sentinel: 1;" in out
    assert ".sam-owned-sentinel { color: #abc; }" in out


def test_unsupported_branding_attribute_rejects_the_render(monkeypatch):
    """Req 3.4 on the render path: a branding values mapping carrying an unsupported attribute is
    rejected by Layer 2 (`UnsupportedAttributeError`) and NO page styling is produced — the render
    raises rather than silently dropping the bad key. On the publish path this surfaces before the
    artifact write, so a bad slice never replaces the previously published form (Req 5.5).
    """
    import pytest

    from sam.shared.page_styles import UnsupportedAttributeError

    with pytest.raises(UnsupportedAttributeError):
        render_application_form_page(
            _config(fields=[{"key": "name"}]),
            head_meta={"title": "x"},
            branding={"color_primary": "#123456", "not_a_real_attribute": "boom"},
        )


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


# ── bugfix bugfix-published-form-submit Task 3.1 — slug + public_api_base plumbing ──────────
#
# Task 3.1 threads `slug` + `public_api_base` through the render entry point; Task 3.2 (below)
# consumes them in the embedded submit <script>. These pin that the params are accepted and that
# the threaded values land as HTML-escaped `data-*` attributes on the form (never interpolated
# into JS — the XSS-safety guarantee).


def test_render_accepts_slug_and_public_api_base_params():
    """R2.6 plumbing: the render entry point accepts `slug` + `public_api_base` kwargs."""
    cfg = _config(fields=[{"key": "email", "type": "email", "label": {"nl": "E-mail"}}])
    out = render_application_form_page(
        cfg,
        head_meta={"title": "Aanmelden"},
        slug="hdcn-aanmelden",
        public_api_base="https://api.example.test",
    )
    assert out.startswith("<!DOCTYPE html>")
    assert 'class="application-form"' in out


def test_slug_and_api_base_land_as_escaped_data_attributes_on_the_form():
    """Task 3.2: the threaded slug + api base are emitted as `data-*` attributes (XSS-safe).

    The submit script reads them off `form.dataset`; they are never interpolated into the inline
    JS. A value carrying HTML-significant characters is HTML-escaped in the attribute, so it can
    never break out of the markup (defence in depth — both are controlled, but escaped anyway).
    """
    body = build_form_body_html(
        _config(fields=[{"key": "name"}]),
        slug="hdcn-aanmelden",
        public_api_base="https://api.example.test",
    )
    assert 'data-slug="hdcn-aanmelden"' in body
    assert 'data-api-base="https://api.example.test"' in body
    # An adversarial value is escaped, not emitted raw:
    hostile = build_form_body_html(
        _config(fields=[{"key": "name"}]),
        slug='x" onx="y',
        public_api_base="x",
    )
    assert 'data-slug="x&quot; onx=&quot;y"' in hostile
    assert '" onx="y' not in hostile.split("<script")[0]


# ── bugfix bugfix-published-form-submit Task 3.2 — the embedded submit script + format checks ──
#
# Task 3.2 replaces the bare no-JS `<form method="post">` dead end with a form whose submit is
# handled by an embedded vanilla-JS `<script>`: it `preventDefault`s the native POST, runs the
# client-side `required` + `format` (EMAIL / IBAN) checks, serializes the backend JSON shape, and
# `fetch`es `POST {public_api_base}/public/members/{slug}/applications`, mapping the response
# (success / inline 422 / neutral). It also reads each field's `format.checker` token off a
# `data-format` attribute (never interpolating config into the JS).


def test_submit_script_prevents_native_post_and_fetches_backend_json():
    """R2.1/R2.2: the body emits a preventDefault'ed submit script that POSTs JSON to the backend."""
    body = build_form_body_html(
        _config(fields=[{"key": "email", "type": "email"}]),
        slug="hdcn-aanmelden",
        public_api_base="https://api.example.test",
    )
    assert "<script" in body
    assert "preventDefault" in body
    assert "fetch(" in body
    # The backend endpoint path template is present (the slug is substituted in JS from the DOM):
    assert "/public/members/{slug}/applications" in body
    # JSON content type + the backend body shape keys:
    assert '"Content-Type": "application/json"' in body
    assert "JSON.stringify" in body
    for shape_key in ("fields", "locale", "consent", "session_key", "website"):
        assert shape_key in body
    # The native POST must never fire — the form is novalidate + JS-handled.
    assert "novalidate" in body


def test_submit_script_maps_422_per_field_errors_and_neutral_states():
    """R2.2: the response handler maps a 422 per-field array inline and shows neutral 404 copy.

    The handler reads the backend's RFC-9457 `errors:[{field,...,detail}]` array (public_app.py
    `_field_errors_array`) and never leaks internal detail on the non-probeable 404 / other states.
    """
    body = build_form_body_html(
        _config(fields=[{"key": "email", "type": "email"}]),
        slug="s",
        public_api_base="https://api.example.test",
    )
    assert "response.status === 422" in body
    assert "data.errors" in body
    assert "entry.field" in body
    # Round 5: the message is chosen by the entry's CODE (Dutch); server text is never rendered.
    assert "entry.code" in body
    assert "entry.detail" not in body
    # Messages are rendered via textContent (never assigned to innerHTML) — no markup
    # injection. (The word "innerHTML" may appear in a comment; what
    # matters is that no `.innerHTML =` SINK is used.)
    assert "textContent" in body
    assert ".innerHTML" not in body


def test_format_token_emitted_as_data_attribute_and_checks_wired():
    """R2.3: a field's `format.checker` is emitted as a `data-format` attr; the EMAIL/IBAN client
    checks mirror field_formats (EMAIL regex, IBAN ISO-13616 mod-97) and run in the submit script.
    """
    body = build_form_body_html(
        _config(
            fields=[
                {"key": "iban", "type": "text", "format": {"checker": "IBAN"}},
                {"key": "email", "type": "email", "format": {"checker": "EMAIL"}},
            ]
        )
    )
    # The token rides on the control as a data-* attribute (read from the DOM, not interpolated):
    assert 'data-format="IBAN"' in body
    assert 'data-format="EMAIL"' in body
    # The client checks mirror the field_formats registry semantics:
    assert "ibanMod97" in body  # ISO 13616 / ISO 7064 mod-97 checksum (not a regex)
    assert "EMAIL_RE" in body  # the platform email pattern
    assert "CHECKERS" in body and "data-format" in body


def test_format_checker_token_in_data_attribute_is_html_escaped():
    """XSS: a malformed/hostile `format.checker` token is HTML-escaped in the data attribute and
    never breaks out of the attribute or into the inline JS."""
    body = build_form_body_html(
        _config(fields=[{"key": "x", "format": {"checker": '"><img src=x>'}}])
    )
    # The hostile token is escaped inside the attribute; the raw break-out form never appears in
    # the field markup region (before the static submit script).
    field_region = body.split("<script")[0]
    assert '"><img src=x>' not in field_region
    assert "&quot;&gt;&lt;img" in body


def test_field_with_no_format_emits_no_data_format_attribute():
    """Preservation: a field with no `format` token renders with NO `data-format` attribute (the
    already-correct render output for plain fields is unchanged)."""
    body = build_form_body_html(_config(fields=[{"key": "name", "type": "text"}]))
    assert "data-format" not in body.split("<script")[0]


def test_build_form_body_html_accepts_slug_and_public_api_base_params():
    """The body builder accepts the threaded params and wires them into the submit script target."""
    body = build_form_body_html(
        _config(fields=[{"key": "name"}]),
        slug="hdcn-aanmelden",
        public_api_base="https://api.example.test",
    )
    assert 'data-slug="hdcn-aanmelden"' in body
    assert 'data-api-base="https://api.example.test"' in body


# ── bugfix bugfix-published-form-submit Task 3.3 — consent control + locale selector ──────────
#
# Task 3.3 renders the two controls the backend submit contract REQUIRES (bugfix.md R2.4): a
# consent checkbox BOUND to the config's `notice.version`, and a locale `<select>` whose options
# are the config's `locales`. The embedded submit script from Task 3.2 reads them off the DOM
# (`collect()` queries `[name="consent"]` + `[name="locale"],[name="lang"]`), so rendering these
# controls is what populates the posted `consent` + `locale`. Both reuse the shared
# `LandingPageStyles` look via the existing `form-group` section + a `form-meta-field` wrapper
# (R2.5 — no new CSS source), and neither carries a ` required` attribute (preservation invariant).


def _config_with_notice(version, *, fields=None, locales=None):
    """A get_public_field_config-shaped dict carrying a real `notice.version` + `locales`."""
    return {
        "tenant_id": "h-dcn",
        "fields": fields if fields is not None else [{"key": "name"}],
        "functional_groups": [],
        "locales": locales if locales is not None else ["nl", "en"],
        "notice": {"version": version},
    }


def test_locale_selector_rendered_with_options_from_config_locales():
    """R2.4: a `<select name="locale">` is rendered with an option per config `locales` code, the
    FIRST selected by default — the submit script reads the chosen value into `locale`."""
    body = build_form_body_html(_config_with_notice("v1", locales=["nl", "en", "de"]))
    assert '<select id="locale" name="locale">' in body
    assert '<option value="nl" selected>nl</option>' in body
    assert '<option value="en">en</option>' in body
    assert '<option value="de">de</option>' in body
    # The submit script's `collect()` reads a control named `locale`:
    assert 'name="locale"' in body


def test_locale_selector_defaults_to_nl_when_locales_empty():
    """Degrade-gracefully: an empty `locales` still renders a locale selector defaulting to nl."""
    cfg = _config_with_notice("v1", locales=[])
    body = build_form_body_html(cfg)
    assert '<select id="locale" name="locale">' in body
    assert '<option value="nl" selected>nl</option>' in body


def test_locale_codes_are_html_escaped_in_the_selector():
    """XSS: a config-origin locale code is HTML-escaped inside the `<option>` (never raw markup)."""
    body = build_form_body_html(
        _config_with_notice("v1", locales=["nl", '"><img src=x>'])
    )
    assert "&quot;&gt;&lt;img" in body
    assert '"><img src=x>' not in body.split("<script")[0]


def test_consent_checkbox_bound_to_notice_version():
    """R2.4: a consent checkbox carries the config's `notice.version` via `data-notice-version` so
    the submit script stamps `consent` with that version (the backend requires it)."""
    body = build_form_body_html(_config_with_notice("notice-v3"))
    assert '<input type="checkbox" id="consent" name="consent"' in body
    assert 'data-notice-version="notice-v3"' in body
    # The submit script reads the version off the control (Task 3.2 `collect()`):
    assert 'getAttribute("data-notice-version")' in body


def test_no_consent_control_when_notice_version_absent():
    """Degrade-gracefully (R2.4): with no notice version there is nothing to consent to, so NO
    consent control is rendered — the notice-less render output is unchanged."""
    body_none = build_form_body_html(_config())  # notice.version is None
    assert 'name="consent"' not in body_none.split("<script")[0]
    assert "data-notice-version" not in body_none.split("<script")[0]
    # A notice that is entirely absent also degrades to no consent control.
    cfg_no_notice = _config()
    del cfg_no_notice["notice"]
    assert (
        'name="consent"' not in build_form_body_html(cfg_no_notice).split("<script")[0]
    )


def test_consent_notice_version_is_html_escaped():
    """XSS: a hostile `notice.version` is HTML-escaped in the `data-notice-version` attribute and
    never breaks out of the attribute into the markup."""
    body = build_form_body_html(_config_with_notice('"><script>alert(1)</script>'))
    # The escaped form is present; the raw break-out never appears before the static submit script.
    assert "data-notice-version=" in body
    assert '"><script>alert(1)</script>' not in body.split("<script>\n(function")[0]


def test_consent_and_locale_reuse_shared_styling_classes():
    """R2.5: both new controls reuse the shared `form-group` section + `form-meta-field` wrapper
    (the shared `LandingPageStyles` look, no new CSS source) — NOT a bolted-on new class."""
    body = build_form_body_html(_config_with_notice("v1"))
    assert '<fieldset class="form-group" data-group="_meta">' in body
    # Exactly two meta-control WRAPPERS in the rendered MARKUP — locale + consent. Scope the count
    # to the markup before the embedded submit `<script>` (as the sibling XSS/consent tests in this
    # file already do): Round-2 Task 7.4's inline-error script carries an explanatory comment that
    # quotes `<div class="form-meta-field" data-field="consent">`, so counting the whole body also
    # matches that script PROSE. The invariant is unchanged (two rendered wrappers) — it is just
    # measured against the emitted markup, not a string the script happens to mention.
    markup = body.split("<script")[0]
    assert markup.count('<div class="form-meta-field"') == 2  # locale + consent
    # They live inside the form, before the submit button / script.
    assert body.index('data-group="_meta"') < body.index("Verstuur")


def test_meta_controls_do_not_add_a_required_attribute():
    """Preservation: neither the locale selector nor the consent checkbox emits a ` required`
    attribute, so they never inflate the `body.count(" required")` field-required invariant."""
    # A config with exactly one required field + the two meta controls -> still exactly one
    # ` required` substring (only the field's).
    body = build_form_body_html(
        _config_with_notice(
            "v1", fields=[{"key": "email", "type": "email", "required": True}]
        )
    )
    assert body.count(" required") == 1


def test_meta_controls_are_not_counted_as_config_fields():
    """steering 39 / preservation: the submit-contract controls use `form-meta-field`, NOT the
    field `form-field` class — so a `form-field` field-count reflects ONLY the tenant's fields."""
    body = build_form_body_html(
        _config_with_notice("v1", fields=[{"key": "a"}, {"key": "b"}])
    )
    assert body.count('class="form-field"') == 2  # only the two config fields
