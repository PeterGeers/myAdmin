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


def _render_field(field: Mapping[str, Any], locale: str) -> str:
    """Render one applicant-facing field to an escaped ``<label>`` + input/select fragment.

    Server-authoritative + XSS-safe: EVERY value that originates from config
    (``key``/``label``/``options``) is HTML-escaped before it enters markup (the shell's
    body is emitted verbatim by ``render_page``, so escaping is this module's job). The
    ``required`` flag is the application-requiredness from the public schema (R4b.6).
    """
    key = _html.escape(str(field.get("key", "")))
    field_type = str(field.get("type", "text"))
    label_text = _html.escape(_label_for(field, locale))
    required = bool(field.get("required"))
    required_attr = " required" if required else ""
    required_mark = ' <span aria-hidden="true">*</span>' if required else ""

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
            f'<select id="{key}" name="{key}"{required_attr}>\n'
            + "\n".join(f"    {o}" for o in options)
            + "\n  </select>"
        )
    elif field_type in ("textarea", "multiline"):
        control = f'<textarea id="{key}" name="{key}"{required_attr}></textarea>'
    else:
        input_type = {
            "email": "email",
            "number": "number",
            "date": "date",
            "tel": "tel",
            "phone": "tel",
        }.get(field_type, "text")
        control = (
            f'<input type="{input_type}" id="{key}" name="{key}"{required_attr} />'
        )

    return (
        f'<div class="form-field" data-field="{key}">\n'
        f'  <label for="{key}">{label_text}{required_mark}</label>\n'
        f"  {control}\n"
        f"</div>"
    )


def build_form_body_html(
    public_field_config: Mapping[str, Any],
    *,
    locale: str = "nl",
    header_html: str = "",
    footer_html: str = "",
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
            output, reused, never a re-derived field list.
        locale: the applicant locale for labels (default ``nl``, R5.3/R6b).
        header_html / footer_html: optional already-composed, trusted fragments the caller
            (publish service) supplies; emitted verbatim around the form.

    Returns:
        The ``<body>`` inner HTML (NOT a full document — ``render_page`` wraps it).
    """
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
    parts = [
        p
        for p in (
            header_html,
            f'<main>\n<form class="application-form" method="post">\n{form_inner}\n<button type="submit">Verstuur</button>\n</form>\n</main>',
            footer_html,
        )
        if p
    ]
    return "\n".join(parts)


def render_application_form_page(
    public_field_config: Mapping[str, Any],
    *,
    head_meta: Mapping[str, str],
    branding: Mapping[str, Any] | None = None,
    locale: str = "nl",
    header_html: str = "",
    footer_html: str = "",
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
    )

    # The shared, plane-neutral shell owns the scaffold; we supply head + body + css.
    return render_page(head_meta=head_meta, body_html=body_html, css=css)
