"""
Plane-neutral, dependency-free HTML page shell (spec 14 / D-RENDER, R7).

``render_page(head_meta, body_html, css)`` composes the generic public-page HTML
scaffold — the ``<!DOCTYPE html>`` + ``<head>`` SEO/OG/Twitter/canonical meta block,
the ``<style>`` wrapper around a caller-supplied CSS string, and a ``<body>`` wrapper
around a caller-supplied body fragment. It is the shared shell both planes compose
their page from:

- **SAM plane (now):** the application-form producer renders its form body via
  ``ApplicationFormRenderer`` and wraps it with ``render_page`` (spec 14 Task 2.2 / 5.1).
- **Flask landing plane (future):** ``generate_index_html`` in
  ``backend/src/services/landing_page_publish_service.py`` is a pure f-string over the
  SAME scaffold; it can share this library back in a LATER spec. **This spec does NOT
  touch the Flask landing module** (🚫 Scope decision; R7.2) — this module is extracted
  from a COPY of that shell logic, and the live Flask function keeps calling its own code.

Design contract (D-RENDER):

- **PLANE-NEUTRAL + DEPENDENCY-FREE.** Only stdlib (``html``) + ``typing`` are imported.
  No Flask, no boto3, no DB, no SAM-specific imports. This is a pure-function library:
  "share the mechanism, not the store" (R7.3 / steering 35).
- **``LandingPageStyles`` stays the single CSS source** — it is NOT imported or forked
  here. ``render_page`` takes the already-generated CSS string as the ``css`` PARAMETER,
  so the caller invokes ``LandingPageStyles`` (the one shared, ``re``/``typing``-only CSS
  generator in ``backend/src/services/landing_page_styles.py``) and passes its output in.
  That keeps this module truly dependency-free while CSS has exactly one source of truth.

Packaging decision (spec 14 Task 2.1) — see
``.kiro/specs/Members/14 - public-pages-multi-tenant-serving/task-2.1-page-shell-decision.md``:
vendored in ``sam/shared/`` (the ``sam/shared``-style vendor named in D-RENDER). The
Members Lambda layer already rsyncs ``sam/shared/`` wholesale (``sam/members/layer/Makefile``),
so this module ships to Lambda with NO build change. ``sam/shared`` is self-contained
(no ``backend/src`` dependency), and because this module is dependency-free the future
Flask landing plane can import it unchanged when it shares back.
"""

import html as _html
from collections.abc import Mapping

__all__ = ["HeadMeta", "render_page"]

# A HeadMeta is a plain mapping of the SEO/OG/Twitter/canonical scaffold fields. Kept as
# a Mapping (not a dataclass) so it stays stdlib-only and any producer can hand in a dict.
HeadMeta = Mapping[str, str]

# The recognised head-meta keys (all optional; a missing key renders as an empty string,
# mirroring the Flask shell's ``.get(..., "")`` behaviour so output parity holds):
#   lang         <html lang="..">            (default "nl")
#   title        <title> + og:title + twitter:title
#   description  meta description + og/twitter description
#   og_image     og:image + twitter:image
#   canonical    og:url + <link rel=canonical>
#   site_name    og:site_name
#   font_links   pre-built <link> tags for web fonts (already HTML; NOT escaped)
#   og_locale    og:locale                   (default "nl_NL")


def _esc(value: str | None) -> str:
    """HTML-escape a meta value; ``None``/missing becomes ``""`` (parity with Flask shell)."""
    if not value:
        return ""
    return _html.escape(value)


def render_page(head_meta: HeadMeta, body_html: str, css: str) -> str:
    """Compose the plane-neutral public-page HTML shell.

    Args:
        head_meta: SEO/OG/Twitter/canonical scaffold values (see the key list above).
            Each recognised value is HTML-escaped here EXCEPT ``font_links``, which is
            already-built ``<link>`` markup and is emitted verbatim (parity with the
            Flask shell, where ``LandingPageStyles.build_font_links`` produces the tags).
        body_html: the page body fragment (header + content + footer + any inline JS),
            already composed and trusted by the caller. Emitted verbatim inside ``<body>``.
        css: the CSS text (e.g. ``LandingPageStyles.build_css_variables`` +
            ``build_page_css``), emitted verbatim inside a single ``<style>`` block.
            ``LandingPageStyles`` is the ONE CSS source — this module never generates CSS.

    Returns:
        A complete ``<!DOCTYPE html>`` document string.
    """
    lang = _esc(head_meta.get("lang")) or "nl"
    title = _esc(head_meta.get("title"))
    description = _esc(head_meta.get("description"))
    og_image = _esc(head_meta.get("og_image"))
    canonical = _esc(head_meta.get("canonical"))
    site_name = _esc(head_meta.get("site_name"))
    og_locale = _esc(head_meta.get("og_locale")) or "nl_NL"

    # font_links is pre-built <link> markup (from the CSS source), not a plain value:
    # emit verbatim, matching the Flask shell. A leading space keeps the head tidy.
    raw_font_links = head_meta.get("font_links", "")
    font_links_html = f"\n  {raw_font_links}" if raw_font_links else ""

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="{description}" />{font_links_html}
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:site_name" content="{site_name}" />
  <meta property="og:locale" content="{og_locale}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{og_image}" />
  <link rel="canonical" href="{canonical}" />
  <style>
{css}
  </style>
</head>
<body>
{body_html}
</body>
</html>"""
