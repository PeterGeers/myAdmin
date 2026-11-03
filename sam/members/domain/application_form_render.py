"""
Spec 14 Task 2.2 — the SAM application-form **shell renderer** (design §C2/C3 / R7).

This is the SAM plane's wiring of the shared, plane-neutral rendering library
(:func:`sam.shared.page_shell.render_page`, extracted in Task 2.1): it composes the
PUBLISHED application-form page HTML by handing ``render_page`` the three things the
shell needs — ``head_meta`` (SEO/OG/canonical), ``body_html`` (the form body), and
``css`` — and letting the shared shell own the ``<!DOCTYPE html>`` + ``<head>`` +
``<style>`` + ``<body>`` scaffold. "Share the mechanism, not the store" (R7.3 /
steering 35): this module imports a pure-function LIBRARY, never calls another plane.

What this module owns vs what the shared library owns
-----------------------------------------------------
- :func:`sam.shared.page_shell.render_page` owns the GENERIC scaffold (head meta block,
  the single ``<style>`` wrapper, the ``<body>`` wrapper) — plane-neutral, dependency-free.
- THIS module owns the SAM-plane composition: it builds the ``head_meta`` dict from the
  tenant's form/branding, renders the applicant-facing form BODY from the public field
  config (:meth:`get_public_field_config`, the single filter authority, reused — never a
  second field list), and produces the ``css`` string from ``LandingPageStyles``.

`LandingPageStyles` stays the SINGLE CSS source (R7.1)
------------------------------------------------------
The CSS is produced here by calling ``LandingPageStyles.build_css_variables`` +
``build_page_css`` (the one shared, ``re``/``typing``-only CSS generator in
``backend/src/services/landing_page_styles.py``) and passing the result to ``render_page``
as the ``css`` PARAMETER. This module does NOT fork, duplicate, or re-implement any CSS —
there is exactly one CSS source for both planes. (`LandingPageStyles` is vendored into the
Members Lambda layer the same least-surface ``cp`` way ``dynamodb_client.py`` is — see
``sam/members/layer/Makefile`` — so it resolves at Lambda runtime without pulling in the
rest of ``backend/src``.)

Scope boundary (Task 2.2 ≠ the gated live write)
------------------------------------------------
This module RENDERS the artifact string only. Writing ``{slug}/index.html`` +
``{slug}/form.json`` to the shared ``myadmin-public-pages-{env}`` bucket and invalidating
CloudFront is the LIVE write — it stays GATED on the owner-run hosting migration
(spec 14 Tasks 8/9, R6.4). The publish service (:mod:`application_publish`) calls this
renderer to produce the HTML; the live S3 put remains dormant until the gated task.

🚫 Flask landing module NOT touched (Scope decision / R7.2)
-----------------------------------------------------------
The Flask ``generate_index_html`` (``landing_page_publish_service.py``) is NOT refactored
by this spec. ``page_shell`` was extracted from a COPY of that shell logic (Task 2.1); the
live Flask function keeps calling its own code. **FUTURE opportunity (R7.2, a LATER spec,
NOT done here):** because ``page_shell`` is plane-neutral and dependency-free, the Flask
landing plane can eventually share it back — ``generate_index_html`` would compose its
landing body + the same ``LandingPageStyles`` CSS through the SAME ``render_page`` — so the
shell scaffold has ONE implementation across both planes. That migration is a landing-module
change and is explicitly out of scope for this spec.
"""

from __future__ import annotations

import html as _html
from collections.abc import Mapping, Sequence
from typing import Any

from sam.shared.page_shell import render_page

__all__ = ["render_application_form_page", "build_form_body_html"]

# Fallback brand colours (match the Flask shell's defaults so a tenant with no branding
# still renders a coherent, on-brand page — parity with generate_index_html).
_DEFAULT_COLOR_PRIMARY = "#2D5F8A"
_DEFAULT_COLOR_ACCENT = "#F4A261"


def _label_for(field: Mapping[str, Any], locale: str) -> str:
    """Pick a field's label in the applicant locale, defaulting to ``nl`` then the key.

    Mirrors the public schema's label contract (``label{nl,en}``, R5.3/R6b): choose the
    chosen locale, fall back to ``nl``, then to any present label, then the bare ``key``.
    """
    label = field.get("label")
    if isinstance(label, Mapping):
        for candidate in (locale, "nl"):
            value = label.get(candidate)
            if value:
                return str(value)
        for value in label.values():
            if value:
                return str(value)
    return str(field.get("key", ""))


def _format_checker_token(field: Mapping[str, Any]) -> str:
    """Return the field's ``format.checker`` token (e.g. ``IBAN`` / ``EMAIL``) or ``""``.

    The public field config emits an optional ``format = {checker, params}`` sub-object per field
    (``_serialize_public_field`` sets ``payload["format"]``). This reads the ``checker`` token so
    :func:`_render_field` can expose it to the client as a ``data-format`` attribute — the submit
    script runs the matching client-side check (bugfix ``bugfix-published-form-submit`` Task 3.2 /
    R2.3), mirroring the ``field_formats`` registry semantics; the server 422 stays authoritative.

    A missing / malformed ``format`` (not a mapping, or no ``checker``) degrades to ``""`` — the
    field simply carries no client check (parity with the read-time degrade-to-``None``, R7.3).
    The token is read as DATA only; it is HTML-escaped by the caller before it enters markup, so a
    stray token can never break out of the attribute.
    """
    fmt = field.get("format")
    if isinstance(fmt, Mapping):
        checker = fmt.get("checker")
        if isinstance(checker, str) and checker.strip():
            return checker.strip()
    return ""


def _render_field(field: Mapping[str, Any], locale: str) -> str:
    """Render one applicant-facing field to an escaped ``<label>`` + input/select fragment.

    Server-authoritative + XSS-safe: EVERY value that originates from config
    (``key``/``label``/``options``/``format.checker``) is HTML-escaped before it enters markup
    (the shell's body is emitted verbatim by ``render_page``, so escaping is this module's job).
    The ``required`` flag is the application-requiredness from the public schema (R4b.6).

    The optional ``format.checker`` token the config emits (``IBAN`` / ``EMAIL``) is exposed as a
    ``data-format`` attribute on the control (bugfix Task 3.2 / R2.3) — NEVER interpolated into
    the submit script's JS. The script reads ``data-format`` off the DOM and runs the matching
    client-side check (mirroring the ``field_formats`` registry), so a config-origin token stays
    DATA behind an HTML-escaped attribute and cannot inject script. The server 422 remains the
    authoritative backstop.
    """
    key = _html.escape(str(field.get("key", "")))
    field_type = str(field.get("type", "text"))
    label_text = _html.escape(_label_for(field, locale))
    required = bool(field.get("required"))
    required_attr = " required" if required else ""
    required_mark = ' <span aria-hidden="true">*</span>' if required else ""
    # The format token is emitted as a `data-format` attribute (escaped) ONLY — the submit script
    # reads it from the DOM; it is never interpolated into JS (XSS-safe). Empty token -> no attr,
    # so a field with no `format` renders byte-identically to before (preservation contract).
    checker = _format_checker_token(field)
    format_attr = f' data-format="{_html.escape(checker)}"' if checker else ""

    # A selectable field's vocabulary is the canonical `options` the public field config emits
    # (`_public_field_options` -> list of `{value, label{nl,en}, order?}`); the retired bare
    # `choices` key is never read here (03a single-vocabulary rule). Pick the locale label with
    # nl fallback then the bare value; HTML-escape both value and label before they enter markup.
    config_options = field.get("options")
    if (
        config_options
        and isinstance(config_options, Sequence)
        and not isinstance(config_options, (str, bytes))
    ):
        options = ['<option value=""></option>']
        for option in config_options:
            if isinstance(option, Mapping):
                raw_value = option.get("value", option.get("key", ""))
                raw_label = option.get("label", raw_value)
                if isinstance(raw_label, Mapping):
                    raw_label = (
                        raw_label.get(locale) or raw_label.get("nl") or raw_value
                    )
            else:
                raw_value = raw_label = option
            value = _html.escape(str(raw_value))
            text = _html.escape(str(raw_label))
            options.append(f'<option value="{value}">{text}</option>')
        control = (
            f'<select id="{key}" name="{key}"{required_attr}{format_attr}>\n'
            + "\n".join(f"    {o}" for o in options)
            + "\n  </select>"
        )
    elif field_type in ("textarea", "multiline"):
        control = (
            f'<textarea id="{key}" name="{key}"{required_attr}{format_attr}></textarea>'
        )
    else:
        input_type = {
            "email": "email",
            "number": "number",
            "date": "date",
            "tel": "tel",
            "phone": "tel",
        }.get(field_type, "text")
        control = (
            f'<input type="{input_type}" id="{key}" name="{key}"'
            f"{required_attr}{format_attr} />"
        )

    return (
        f'<div class="form-field" data-field="{key}">\n'
        f'  <label for="{key}">{label_text}{required_mark}</label>\n'
        f"  {control}\n"
        f"</div>"
    )


def _render_locale_selector(public_field_config: Mapping[str, Any]) -> str:
    """Render the locale `<select>` from the config's ``locales`` list (bugfix Task 3.3 / R2.4).

    The backend REQUIRES a ``locale`` on submit; the embedded submit script reads the chosen value
    from a control named ``locale`` (``collect()`` queries ``[name="locale"], [name="lang"]``). This
    renders a `<select name="locale">` whose options are exactly the config's ``locales`` codes, the
    FIRST selected by default (falling back to ``nl`` when the list is empty). Every option value is
    HTML-escaped (the codes are config-origin DATA), so a stray code can never break out of markup.

    Styled with the SAME ``<label>`` + control structure and the shared ``LandingPageStyles`` look
    as every other control (R2.5 — no new CSS source). It uses the ``form-meta-field`` wrapper class
    (a sibling of the field ``form-field`` class) so it is visually consistent yet is NOT counted as
    a config FIELD by the preservation field-count invariant (the locale selector is a submit-contract
    control, not a tenant field). No ``required`` attribute is emitted (a default is always selected),
    so the preservation ``body.count(" required")`` invariant is untouched.
    """
    raw_locales = public_field_config.get("locales")
    locales: list[str] = []
    if (
        raw_locales
        and isinstance(raw_locales, Sequence)
        and not isinstance(raw_locales, (str, bytes))
    ):
        for loc in raw_locales:
            code = str(loc).strip()
            if code and code not in locales:
                locales.append(code)
    if not locales:
        locales = ["nl"]

    options: list[str] = []
    for index, code in enumerate(locales):
        value = _html.escape(code)
        selected = " selected" if index == 0 else ""
        options.append(f'<option value="{value}"{selected}>{value}</option>')

    return (
        '<div class="form-meta-field" data-field="locale">\n'
        '  <label for="locale">Taal</label>\n'
        '  <select id="locale" name="locale">\n'
        + "\n".join(f"    {o}" for o in options)
        + "\n  </select>\n"
        "</div>"
    )


def _notice_text_for(notice: Mapping[str, Any], locale: str) -> str:
    """Pick the consent notice body in the applicant locale, defaulting to ``nl`` (bugfix Round-2
    Task 7.3 / R5.3).

    The Round-2 surfacing (Task 7.2) serves the FULL notice ``{version, text}`` where ``text`` is a
    locale→string map (e.g. ``{"nl": "...", "en": "..."}``). This mirrors :func:`_label_for`'s
    locale/``nl`` fallback contract exactly: choose the chosen locale, fall back to ``nl``, then to
    any present non-blank body. A missing / malformed ``text`` (not a mapping, or no non-blank body)
    degrades to ``""`` — the control then renders the checkbox with no notice paragraph (parity with
    the label degrade). The returned value is config-origin DATA and is HTML-escaped by the caller
    before it enters markup.
    """
    text = notice.get("text")
    if isinstance(text, Mapping):
        for candidate in (locale, "nl"):
            value = text.get(candidate)
            if value and str(value).strip():
                return str(value)
        for value in text.values():
            if value and str(value).strip():
                return str(value)
    return ""


def _render_consent_control(
    public_field_config: Mapping[str, Any], locale: str = "nl"
) -> str:
    """Render the localized consent notice TEXT + checkbox bound to ``notice.version`` (bugfix
    Round-2 Task 7.3 / R5.3, R6.4; builds on Round-1 Task 3.3 / R2.4).

    The backend REQUIRES a ``consent`` object on submit and stamps the authoritative consent record
    against the notice version; a submit without it is hard-rejected. The Round-2 surfacing serves
    the FULL notice ``{version, text}`` (``text`` a locale→string map). When a notice IS present
    this renders, in order:

      1. the localized ``text[locale]`` (``nl`` fallback, :func:`_notice_text_for`), HTML-escaped,
         as a ``<p class="consent-notice-text">`` ABOVE the checkbox so the applicant can READ what
         they are accepting (Round-2 Defect 2 — the text was previously not served/rendered, so
         consent was posted empty → 422 ``CONSENT_REQUIRED``);
      2. the ``<input type="checkbox" name="consent">`` carrying the version as a
         ``data-notice-version`` attribute — the embedded submit script reads ``consentEl.checked``
         + ``consentEl.getAttribute("data-notice-version")`` into the posted ``consent`` object
         (``collect()``).

    EVERY config-origin value (the notice ``text`` body and the ``version``) is HTML-escaped so it
    can never break out of markup (steering 39 — config-origin values escaped). Localization reuses
    the SAME locale/``nl`` fallback as field labels (:func:`_label_for`).

    Degrade-gracefully contract (unchanged, empty-is-valid): a missing ``notice`` or a ``None``/empty
    version means there is no notice to consent to, so NO consent control is rendered (returns
    ``""``) — the already-correct notice-LESS render output stays byte-identical (the Round-2
    preservation golden config carries ``notice.version = None`` and therefore renders nothing).
    When a notice IS present the checkbox is rendered whenever there is a version, so consent can be
    given even if a locale body happens to be blank (the text paragraph is simply omitted then).

    Styled with the SAME shared ``LandingPageStyles`` look as every other control (R2.5/R6.4 — no
    new CSS source): the wrapper reuses the ``form-meta-field`` class (a sibling of the field
    ``form-field`` class) so it is visually consistent yet is NOT counted as a config FIELD by the
    preservation field-count invariant, and the notice paragraph reuses the shared ``<p>`` typography.
    No ``required`` attribute is emitted (the server is the authoritative enforcer of consent), so
    the preservation ``body.count(" required")`` invariant is untouched.
    """
    notice = public_field_config.get("notice")
    version = ""
    if isinstance(notice, Mapping):
        raw_version = notice.get("version")
        if raw_version is not None and str(raw_version).strip():
            version = str(raw_version).strip()
    if not version:
        return ""

    version_attr = _html.escape(version)
    # The localized notice body (nl fallback) is config-origin DATA — HTML-escaped before it enters
    # markup. An absent/blank body degrades to no paragraph; the checkbox still renders so consent
    # can be given (the version is the binding, the text is the human-readable explanation).
    notice_text = _notice_text_for(notice, locale) if isinstance(notice, Mapping) else ""
    notice_paragraph = (
        f'  <p class="consent-notice-text">{_html.escape(notice_text)}</p>\n'
        if notice_text
        else ""
    )
    return (
        '<div class="form-meta-field" data-field="consent">\n'
        f"{notice_paragraph}"
        '  <label for="consent">\n'
        f'    <input type="checkbox" id="consent" name="consent" data-notice-version="{version_attr}" />\n'
        "    Ik ga akkoord\n"
        "  </label>\n"
        "</div>"
    )


def build_form_body_html(
    public_field_config: Mapping[str, Any],
    *,
    locale: str = "nl",
    header_html: str = "",
    footer_html: str = "",
    slug: str = "",
    public_api_base: str = "",
) -> str:
    """Compose the application-form ``<body>`` fragment from the PUBLIC field config.

    Renders ONLY what the public schema exposes — the already-filtered ``fields`` list
    (``application_visible`` only, R5.1/R5.2) grouped by the authored ``functional_groups``
    catalog (spec 13 R2 display order) — so no un-whitelisted field can leak into the
    published page. The server stays authoritative: the config is the single source, this
    just projects it to markup.

    Args:
        public_field_config: the ``get_public_field_config`` result (``fields``,
            ``functional_groups``, ``locales``, ``notice``) — the single filter authority's
            output, reused, never a re-derived field list. ``locales`` drives the rendered locale
            selector and ``notice.version`` the consent control (bugfix Task 3.3 / R2.4) — the two
            controls the backend submit contract requires; the submit script reads them off the DOM.
        locale: the applicant locale for labels (default ``nl``, R5.3/R6b).
        header_html / footer_html: optional already-composed, trusted fragments the caller
            (publish service) supplies; emitted verbatim around the form.
        slug: the form's public slug — the single path segment the submit script posts to
            (``POST {public_api_base}/public/members/{slug}/applications``). Threaded through
            from the publish step (bugfix ``bugfix-published-form-submit`` Task 3.1) so a LATER
            task (3.2) can wire the ``preventDefault``ed JSON submit; empty here is backward
            compatible — the current render output is unchanged when it is absent.
        public_api_base: the publish-time-resolved public API base URL (e.g.
            ``https://api.example.com``) the submit script's ``fetch`` targets. Resolved from a
            publish env var with NO silent default (fail-fast — see :mod:`application_publish`);
            threaded through here as DATA only (no network call at render time). Empty here is
            backward compatible — the current render output is unchanged when it is absent.

    Returns:
        The ``<body>`` inner HTML (NOT a full document — ``render_page`` wraps it).
    """
    # Task 3.1 threads `slug` + `public_api_base` so a later task's submit script can target
    # `{public_api_base}/public/members/{slug}/applications`. This task only CARRIES them (the
    # submit <script> is emitted by Task 3.2), so the rendered output is byte-identical when they
    # are absent/empty — the preservation contract. `_ = (...)` keeps them referenced without
    # changing any emitted markup yet.
    _ = (slug, public_api_base)
    fields = public_field_config.get("fields") or []
    groups = public_field_config.get("functional_groups") or []

    # Order sections by the authored group catalog; ungrouped/unknown-group fields fall
    # into a trailing default section (deterministic, parity with the renderer's fallback).
    group_order: list[str] = [str(g.get("key")) for g in groups if g.get("key")]
    group_labels: dict[str, str] = {}
    for g in groups:
        gkey = str(g.get("key", ""))
        label = g.get("label")
        if isinstance(label, Mapping):
            group_labels[gkey] = str(label.get(locale) or label.get("nl") or gkey)
        else:
            group_labels[gkey] = gkey

    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for f in fields:
        gkey = str(f.get("functional_group", "")) or "_ungrouped"
        by_group.setdefault(gkey, []).append(f)

    ordered_keys = [k for k in group_order if k in by_group]
    ordered_keys += [k for k in by_group if k not in group_order]

    sections: list[str] = []
    for gkey in ordered_keys:
        heading = (
            _html.escape(group_labels.get(gkey, "")) if gkey != "_ungrouped" else ""
        )
        heading_html = f"  <h2>{heading}</h2>\n" if heading else ""
        rendered = "\n".join(_render_field(f, locale) for f in by_group[gkey])
        sections.append(
            f'<fieldset class="form-group" data-group="{_html.escape(gkey)}">\n'
            f"{heading_html}{rendered}\n"
            f"</fieldset>"
        )

    form_inner = "\n".join(sections)

    # bugfix Task 3.3 — the two controls the backend submit contract REQUIRES, rendered with the
    # SAME `form-field` / `<label>` structure + shared LandingPageStyles as every other field (no
    # new CSS, R2.5). The submit script (Task 3.2) already reads them off the DOM:
    #   * the locale `<select name="locale">` (options = config `locales`, first selected) ->
    #     `collect()` reads it into `locale`;
    #   * the consent control: the localized `notice.text[locale]` (nl fallback, HTML-escaped) as a
    #     `<p>` ABOVE a `<input type="checkbox" name="consent" data-notice-version=...>` bound to
    #     `notice.version` (bugfix Round-2 Task 7.3) -> `collect()` stamps `consent.accepted` +
    #     `consent.version`; the applicant can now READ the notice before accepting it.
    # Consent degrades to "" when the config has no notice version (parity golden config), so the
    # already-correct notice-less render output is unchanged. Neither control carries a ` required`
    # attribute, so the preservation `body.count(" required")` invariant is untouched.
    locale_selector = _render_locale_selector(public_field_config)
    consent_control = _render_consent_control(public_field_config, locale)
    meta_controls = "\n".join(c for c in (locale_selector, consent_control) if c)
    if meta_controls:
        # Wrap the submit-contract controls in a trailing `<fieldset class="form-group">` so they
        # sit in the SAME section structure and shared styling as the authored field groups (R2.5).
        # `data-group="_meta"` keeps them a distinct, deterministic trailing section — never
        # confused with an authored `functional_group`.
        meta_section = (
            '<fieldset class="form-group" data-group="_meta">\n'
            f"{meta_controls}\n"
            "</fieldset>"
        )
        form_inner = f"{form_inner}\n{meta_section}" if form_inner else meta_section

    # XSS-safe plumbing of the two publish-time values the submit script needs (bugfix Task 3.2):
    # the `slug` (path segment) and the `public_api_base` (env-resolved) are emitted as HTML-escaped
    # `data-*` attributes on the <form>. They are NEVER interpolated into the inline JS — the script
    # reads them off `form.dataset` — so even though both are controlled (not config-origin), a
    # value can never break out of markup OR out of the script string (defence in depth / R3.4).
    slug_attr = _html.escape(slug)
    api_base_attr = _html.escape(public_api_base)
    submit_endpoint = (
        f'<form class="application-form" method="post" novalidate '
        f'data-slug="{slug_attr}" data-api-base="{api_base_attr}">'
    )

    # A status region the submit script writes success / neutral messages into (aria-live so a
    # screen reader announces the outcome). Empty at render; populated only by JS on response.
    status_region = '<div class="form-status" role="status" aria-live="polite"></div>'

    form_html = (
        f"<main>\n{submit_endpoint}\n{form_inner}\n{status_region}\n"
        f'<button type="submit">Verstuur</button>\n</form>\n'
        f"{_SUBMIT_SCRIPT}\n</main>"
    )
    parts = [p for p in (header_html, form_html, footer_html) if p]
    return "\n".join(parts)


# ── The embedded submit script (bugfix bugfix-published-form-submit Task 3.2) ─────────────────
#
# Vanilla JS (no bundler) that runs in the static published page. It is a STATIC constant — it
# reads EVERYTHING it needs from the DOM (`form.dataset.slug` / `form.dataset.apiBase`, each
# field's `name` + `data-format`), so NO config-origin value is ever interpolated into this
# string. That is the XSS-safety guarantee for the script: a malicious config value can only ever
# land in an HTML-escaped attribute, never inside this JS.
#
# On submit it: (a) `preventDefault`s so the native POST to /apply NEVER fires; (b) runs the
# client-side `required` + `format` (EMAIL / IBAN) checks, mapping any failure to an inline
# per-field message; (c) serializes the values into the backend JSON shape — values under
# `fields`, plus `locale` (read from a locale selector if present, else the page lang), `consent`
# (read from a consent control if present — the real consent/locale controls are Task 3.3; until
# then the shape is still correct), an optional `session_key`, and the empty `website` honeypot;
# (d) `fetch`es `POST {apiBase}/public/members/{slug}/applications` with
# `Content-Type: application/json`; (e) maps the response — success state, inline per-field 422
# errors (the backend's RFC-9457 `errors:[{field,...,detail}]` array), and a NEUTRAL message on
# the non-probeable 404 / any other state. No internal detail is surfaced to the applicant.
#
# The EMAIL / IBAN checks mirror `sam/members/domain/field_formats.py` semantics: the EMAIL regex
# is the platform `_EMAIL_PATTERN`; IBAN is the ISO 13616 structural envelope + the mod-97 (ISO
# 7064) checksum computed digit-by-digit (a regex cannot verify the checksum). The server 422
# remains authoritative — these are a convenience.
_SUBMIT_SCRIPT = """<script>
(function () {
  "use strict";
  var form = document.querySelector("form.application-form");
  if (!form) { return; }
  var status = form.querySelector(".form-status");

  // EMAIL — mirrors field_formats._EMAIL_PATTERN (local@domain.tld, >=1 dot in domain).
  var EMAIL_RE = /^[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}$/;
  function checkEmail(value) {
    return EMAIL_RE.test(String(value).trim())
      ? null
      : "Vul een geldig e-mailadres in.";
  }

  // IBAN — mirrors field_formats.check_iban: ISO 13616 structure + mod-97 (ISO 7064) checksum.
  var IBAN_STRUCTURE = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$/;
  function ibanMod97(compact) {
    var rearranged = compact.slice(4) + compact.slice(0, 4);
    var remainder = 0;
    for (var i = 0; i < rearranged.length; i++) {
      var ch = rearranged.charAt(i);
      // 'A'-'Z' -> "10".."35"; '0'-'9' -> the digit itself.
      var chunk = /[A-Z]/.test(ch) ? String(ch.charCodeAt(0) - 55) : ch;
      for (var j = 0; j < chunk.length; j++) {
        remainder = (remainder * 10 + (chunk.charCodeAt(j) - 48)) % 97;
      }
    }
    return remainder;
  }
  function checkIban(value) {
    var compact = String(value).replace(/ /g, "").toUpperCase();
    if (!IBAN_STRUCTURE.test(compact) || ibanMod97(compact) !== 1) {
      return "Vul een geldig IBAN in.";
    }
    return null;
  }

  var CHECKERS = { EMAIL: checkEmail, IBAN: checkIban };

  // The synthetic field key the backend uses for the consent reject (code CONSENT_REQUIRED —
  // `_membership_writes_application._CONSENT_FIELD_KEY`). The wire `code` is the shared
  // `errors.validation.required` i18n leaf, so the RELIABLE runtime signal is the field KEY,
  // not the code — a 422 entry whose `field === "consent"` is the consent-required reject and
  // is mapped to a clear message near the consent control (`[data-field="consent"]`).
  var CONSENT_REQUIRED = "consent";

  function controls() {
    // Every named field control inside the form (inputs / selects / textareas), skipping the
    // honeypot and the submit button.
    return Array.prototype.slice
      .call(form.querySelectorAll("[name]"))
      .filter(function (el) { return el.name && el.name !== "website"; });
  }

  function fieldWrap(el) {
    // The per-field wrapper is `.form-field`; the submit-contract controls (consent, locale)
    // sit in a sibling `.form-meta-field` wrapper (the consent control is
    // `<div class="form-meta-field" data-field="consent">`). Resolve either so the inline
    // message lands inside the control's own wrapper, next to what it refers to.
    var wrap = el.closest ? el.closest(".form-field, .form-meta-field") : null;
    return wrap || el.parentNode;
  }

  function wrapForField(name) {
    // Prefer the control carrying this `name`; fall back to the `[data-field="{name}"]` wrapper
    // (the consent control is addressed by its synthetic `data-field="consent"` key). This lets
    // a server 422 for a synthetic key with no live `[name]` control still resolve a wrapper.
    var el = form.querySelector('[name="' + name + '"]');
    if (el) { return fieldWrap(el); }
    return form.querySelector('[data-field="' + name + '"]');
  }

  function clearErrors() {
    Array.prototype.slice
      .call(form.querySelectorAll(".field-error"))
      .forEach(function (n) { n.parentNode.removeChild(n); });
    if (status) { status.textContent = ""; status.className = "form-status"; }
  }

  function showFieldError(name, message) {
    var wrap = wrapForField(name);
    if (!wrap) { return; }
    var msg = document.createElement("div");
    msg.className = "field-error";
    msg.setAttribute("role", "alert");
    // textContent — NEVER innerHTML — so a server detail string cannot inject markup.
    msg.textContent = message;
    wrap.appendChild(msg);
  }

  function neutral(message) {
    if (status) { status.textContent = message; status.className = "form-status form-status-error"; }
  }

  function clientValidate() {
    var errors = {};
    controls().forEach(function (el) {
      var value = el.value == null ? "" : String(el.value);
      if (el.hasAttribute("required") && !value.trim()) {
        errors[el.name] = "Dit veld is verplicht.";
        return;
      }
      if (!value.trim()) { return; }
      var token = el.getAttribute("data-format");
      var checker = token ? CHECKERS[token] : null;
      if (checker) {
        var problem = checker(value);
        if (problem) { errors[el.name] = problem; }
      }
    });
    return errors;
  }

  function collect() {
    var fields = {};
    controls().forEach(function (el) {
      fields[el.name] = el.value == null ? "" : el.value;
    });
    // Locale: read a locale/lang selector if the page rendered one (Task 3.3); else the page lang.
    var localeEl = form.querySelector('[name="locale"], [name="lang"]');
    var locale = localeEl && localeEl.value
      ? localeEl.value
      : (document.documentElement.getAttribute("lang") || "nl");
    // Consent: read a consent control if present (Task 3.3 wires the real one bound to the notice
    // version); until then an empty object keeps the backend JSON shape correct.
    var consentEl = form.querySelector('[name="consent"]');
    var consent = {};
    if (consentEl) {
      consent.accepted = consentEl.type === "checkbox" ? !!consentEl.checked : !!consentEl.value;
      var version = consentEl.getAttribute("data-notice-version");
      if (version) { consent.version = version; }
    }
    // website is the honeypot — always sent empty from a real browser.
    return {
      fields: fields,
      locale: locale,
      consent: consent,
      session_key: form.getAttribute("data-session-key") || undefined,
      website: ""
    };
  }

  function submitUrl() {
    var base = (form.dataset.apiBase || "").replace(/\\/+$/, "");
    // The backend endpoint is the literal template "/public/members/{slug}/applications" with the
    // slug read from the DOM (`form.dataset.slug`) and URL-encoded — no config value is ever
    // interpolated into this string (XSS-safe). The template literal is kept whole so the path
    // contract is self-evident in the artifact.
    var path = "/public/members/{slug}/applications".replace(
      "{slug}", encodeURIComponent(form.dataset.slug || "")
    );
    return base + path;
  }

  form.addEventListener("submit", function (event) {
    // (a) the native POST to the static /apply page must NEVER fire.
    event.preventDefault();
    clearErrors();

    // (b) client-side presence + format checks (convenience; the server 422 stays authoritative).
    var clientErrors = clientValidate();
    var names = Object.keys(clientErrors);
    if (names.length) {
      names.forEach(function (name) { showFieldError(name, clientErrors[name]); });
      neutral("Controleer de gemarkeerde velden.");
      return;
    }

    // (c)/(d) serialize the backend JSON shape and POST it as JSON.
    var payload = collect();
    fetch(submitUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        // (e) map the response — success / inline 422 / neutral everything-else.
        if (response.ok) {
          form.reset();
          if (status) {
            status.textContent = "Bedankt, je aanmelding is ontvangen.";
            status.className = "form-status form-status-success";
          }
          return;
        }
        if (response.status === 422) {
          // The 422 body is the shared per-field envelope: `{errors:[{field, code, detail}]}`
          // (handler `_field_errors_array`). Map EACH entry inline next to its control by its
          // `field` key; the consent reject arrives on the synthetic `CONSENT_REQUIRED` field
          // key (`consent`) and lands near the consent control (`[data-field="consent"]`). The
          // server `detail` is shown via textContent only (never innerHTML) — no markup inject.
          return response.json().then(function (data) {
            var arr = (data && data.errors) || [];
            if (Array.isArray(arr) && arr.length) {
              var sawConsent = false;
              arr.forEach(function (entry) {
                if (!entry || !entry.field) { return; }
                if (entry.field === CONSENT_REQUIRED) {
                  // Consent-required: a clear, consent-adjacent message near the checkbox.
                  sawConsent = true;
                  showFieldError(
                    CONSENT_REQUIRED,
                    entry.detail || "Je moet akkoord gaan om je aanmelding te versturen."
                  );
                } else {
                  showFieldError(entry.field, entry.detail || "Ongeldige waarde.");
                }
              });
              neutral(
                sawConsent
                  ? "Ga akkoord met de voorwaarden en controleer de gemarkeerde velden."
                  : "Controleer de gemarkeerde velden."
              );
            } else {
              // A 422 with no usable per-field array — treat as a neutral validation nudge.
              neutral("Controleer je gegevens en probeer het opnieuw.");
            }
          }).catch(function () {
            neutral("Controleer je gegevens en probeer het opnieuw.");
          });
        }
        // 404 / 5xx / any other opaque state — deliberately non-probeable, no internal detail.
        neutral("Je aanmelding kon niet worden verwerkt. Probeer het later opnieuw.");
      })
      .catch(function () {
        neutral("Je aanmelding kon niet worden verwerkt. Probeer het later opnieuw.");
      });
  });
})();
</script>"""


def render_application_form_page(
    public_field_config: Mapping[str, Any],
    *,
    head_meta: Mapping[str, str],
    branding: Mapping[str, Any] | None = None,
    locale: str = "nl",
    header_html: str = "",
    footer_html: str = "",
    slug: str = "",
    public_api_base: str = "",
) -> str:
    """Render the full published application-form page via the shared ``page_shell``.

    This is the SAM form's shell-rendering entry point (R7.1 "the SAM form SHALL render its
    shell via ``page_shell``"): build the body from the public field config, produce the CSS
    from ``LandingPageStyles`` (the single CSS source), and hand both plus ``head_meta`` to
    :func:`sam.shared.page_shell.render_page`, which owns the generic document scaffold.

    Args:
        public_field_config: the ``get_public_field_config`` result (the applicant schema).
        head_meta: the SEO/OG/canonical scaffold values ``page_shell`` recognises
            (``title``, ``description``, ``canonical``, ``og_image``, ``site_name``,
            ``font_links``, ``lang``, ``og_locale``). Each value is escaped by ``render_page``.
        branding: optional resolved branding dict (``color_primary``/``color_accent`` +
            typography/spacing) feeding ``LandingPageStyles``; a tenant with no branding gets
            the default palette (parity with the Flask shell).
        locale: the applicant locale for field/group labels (default ``nl``).
        header_html / footer_html: optional trusted fragments wrapped around the form body.
        slug: the form's public slug the submit script posts to — threaded through to
            :func:`build_form_body_html` so a LATER task (3.2) can target
            ``POST {public_api_base}/public/members/{slug}/applications``. Empty here is
            backward compatible (the render output is unchanged when it is absent).
        public_api_base: the publish-time-resolved public API base URL baked into the artifact
            (bugfix ``bugfix-published-form-submit`` Task 3.1). The publish step resolves this
            from a publish env var with NO silent default (fail-fast,
            :mod:`application_publish`) and passes it in so the baked-in base is correct per
            environment rather than silently targeting the wrong backend. Threaded as DATA
            only (no network call at render time); empty here is backward compatible.

    Returns:
        A complete ``<!DOCTYPE html>`` document string (the ``{slug}/index.html`` artifact
        body — the live S3 write of it stays gated, spec 14 Tasks 8/9).
    """
    brand = dict(branding) if branding else {}
    color_primary = str(brand.get("color_primary") or _DEFAULT_COLOR_PRIMARY)
    color_accent = str(brand.get("color_accent") or _DEFAULT_COLOR_ACCENT)

    # LandingPageStyles is the ONE CSS source — imported lazily so this module is importable
    # (and unit-testable) even where the vendored copy is absent, and so page_shell stays the
    # dependency-free core while CSS composition lives on the producer side (R7.1).
    from services.landing_page_styles import LandingPageStyles

    css = "\n".join(
        (
            LandingPageStyles.build_css_variables(brand),
            LandingPageStyles.build_page_css(color_primary, color_accent),
        )
    )

    body_html = build_form_body_html(
        public_field_config,
        locale=locale,
        header_html=header_html,
        footer_html=footer_html,
        slug=slug,
        public_api_base=public_api_base,
    )

    # The shared, plane-neutral shell owns the scaffold; we supply head + body + css.
    return render_page(head_meta=head_meta, body_html=body_html, css=css)
