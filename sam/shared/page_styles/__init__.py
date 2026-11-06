"""
SAM-owned Layer-2 CSS generator — the ``Styling_Logic`` for the Look_And_Feel_Capability
(spec 15 / DD-1, task 1.1).

``render_page_styles(settings) -> PageStyles`` is the ONE reusable Layer-2 function (C1):
it turns a Page's ``Look_And_Feel_Settings`` **values** into that Page's styling output.
It is the SAM-owned source of truth for the CSS-generation logic that previously lived on
the Flask plane as ``backend/src/services/landing_page_styles.py`` (``LandingPageStyles``)
and was build-time vendored into the Members layer (`sam/members/layer/Makefile`). DD-1
**relocates/extracts** that logic here so SAM no longer depends on a Flask-plane module as
its source of truth (Req 3.1), including as a vendored copy.

Design contract (spec 15 design, C1 / C2):

- **Pure and deterministic** — identical values produce identical output (Req 1.2, 1.5).
- **Page-type-agnostic** — reads ONLY the supplied values mapping; holds no
  Application_Form-specific (or any page-specific) state. The same function styles the
  application form today and a future SAM landing page (Req 1.1, 1.4, 6.1, 6.2, 6.3).
- **Ten supported attributes** — the original spec-15 SEVEN (``color_primary``,
  ``color_accent``, ``font_heading``, ``font_body``, ``base_spacing``,
  ``border_radius_global``, ``shadow_style``) PLUS the three the bugfix
  ``bugfix-published-form-styling`` added as a deliberate, documented extension (bugfix 3.4):
  ``columns`` (drives the application-form grid track count), ``logo`` and ``header_title``
  (carried as supported VALUES the renderer consumes — they emit no CSS of their own). Any
  key outside the ten is rejected (Req 3.4). See :data:`SUPPORTED_ATTRIBUTES`.
- **Absent attribute -> SAM-owned default** for that attribute (Req 1.3, 3.3, 4.4, 5.4).
- **Unsupported attribute -> raise** :class:`UnsupportedAttributeError` and produce NO
  styling (Req 3.4).
- **DEPENDENCY-FREE** — only stdlib (``re``) + ``typing`` are imported, like the Flask
  original and the sibling ``sam/shared/page_shell.py``. No Flask, no boto3, no DB, no
  SAM-plane imports — so no runtime read of or call to the Flask plane is possible
  (Req 2.2, 3.5).

``PageStyles`` is a small value object carrying the three CSS pieces Layer 3 (the
renderer) needs — the ``:root`` variables block, the page CSS, and the font ``<link>``
tags — i.e. the three outputs the Flask ``LandingPageStyles`` produced via
``build_css_variables`` / ``build_page_css`` / ``build_font_links``.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "SUPPORTED_ATTRIBUTES",
    "PageStyles",
    "UnsupportedAttributeError",
    "render_page_styles",
]

# ─── The supported attributes — now TEN (Req 3.2 + bugfix 3.4 extension) ────────────────
# The attribute set the SAM-owned styling logic consumes. Any key outside this set is
# unsupported and causes render_page_styles to reject the request (Req 3.4).
#
# The first SEVEN are the original spec-15 contract (colours / fonts / spacing / radius /
# shadow). The bugfix ``bugfix-published-form-styling`` (Req 2.2 / 2.7, design §C) extends
# the set with THREE new values-only attributes — a deliberate, DOCUMENTED extension of the
# exactly-seven set (bugfix 3.4 names this as an allowed extension):
#
#   * ``columns``      — the number of layout columns for the form's field groups; DRIVES
#                        the application-form grid ``grid-template-columns`` track count
#                        (clamped 1..4 here; authoritative out-of-range rejection at the
#                        edge/service plane, Task 10).
#   * ``logo``         — a URL/asset reference to the tenant logo; CARRIED as a supported
#                        value but NOT emitted as CSS — the renderer (Task 6) consumes it.
#   * ``header_title`` — the form header/title text; likewise CARRIED for the renderer, not
#                        emitted as CSS.
#
# ``logo`` / ``header_title`` are accepted so ``render_page_styles`` does not reject them as
# unsupported, but they produce NO CSS of their own (the renderer reads them from the stored
# slice). ``columns`` is the only new attribute that affects the generated CSS. Any key
# OUTSIDE these ten is still rejected (Req 3.4).
SUPPORTED_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {
        "color_primary",
        "color_accent",
        "font_heading",
        "font_body",
        "base_spacing",
        "border_radius_global",
        "shadow_style",
        # bugfix bugfix-published-form-styling (Req 2.2 / 2.7) — the three new values-only
        # attributes; a documented extension of the original seven (bugfix 3.4).
        "columns",
        "logo",
        "header_title",
    }
)

# Default / ceiling for the application-form multi-column grid (bugfix DD-B1). The `columns`
# attribute (now a supported attribute) drives the grid track count; an unset value falls
# back to this sensible multi-column default. The ceiling is a defensive clamp so the
# generator always emits a well-formed track list — the authoritative out-of-range rejection
# lives at the edge/service plane (Task 10).
_DEFAULT_FORM_COLUMNS: Final[int] = 2
_MAX_FORM_COLUMNS: Final[int] = 4

# ─── SAM-owned defaults (Req 1.3, 3.3) ─────────────────────────────────────────────────
# A missing attribute resolves to the default below. These match the fallbacks the Flask
# LandingPageStyles baked into its ``branding.get(key, <default>)`` calls, now owned here
# as the SAM source of truth. color_primary / color_accent had no literal default in the
# Flask caller (they were always supplied), so SAM pins the "professional" theme values —
# the THEME_PRESETS["professional"] colours the Flask plane used as its canonical default.
_DEFAULTS: Final[dict[str, str]] = {
    "color_primary": "#2D5F8A",
    "color_accent": "#F4A261",
    "font_heading": "system",
    "font_body": "system",
    "base_spacing": "normal",
    "border_radius_global": "rounded",
    "shadow_style": "subtle",
    # bugfix bugfix-published-form-styling (Req 2.2 / 2.7 / 3.3) — defaults for the three new
    # attributes. An unset attribute resolves to the default below exactly like the original
    # seven (Req 1.3 / 3.3). ``columns`` defaults to the sensible multi-column count the
    # application-form grid already used before the attribute was authorable; ``logo`` /
    # ``header_title`` default to EMPTY (no logo / no heading rendered) so a tenant that never
    # authored them renders byte-identically to today (preservation 3.3). These are stored as
    # strings alongside the other values; the renderer treats an empty value as "absent".
    "columns": str(_DEFAULT_FORM_COLUMNS),
    "logo": "",
    "header_title": "",
}

# ─── Lookup maps for the CSS-variable attributes (relocated from LandingPageStyles) ─────
_SPACING_MAP: Final[dict[str, dict[str, str]]] = {
    "compact": {"section": "1.5rem", "element": "0.75rem"},
    "normal": {"section": "2rem", "element": "1rem"},
    "relaxed": {"section": "3rem", "element": "1.5rem"},
}

_GLOBAL_RADIUS_MAP: Final[dict[str, dict[str, str]]] = {
    "sharp": {"sm": "0", "md": "0", "lg": "0"},
    "rounded": {"sm": "4px", "md": "8px", "lg": "16px"},
    "pill": {"sm": "12px", "md": "24px", "lg": "9999px"},
}

_SHADOW_MAP: Final[dict[str, dict[str, str]]] = {
    "none": {"card": "none", "hover": "none"},
    "subtle": {
        "card": "0 2px 8px rgba(0,0,0,0.08)",
        "hover": "0 4px 16px rgba(0,0,0,0.12)",
    },
    "medium": {
        "card": "0 4px 12px rgba(0,0,0,0.12)",
        "hover": "0 8px 24px rgba(0,0,0,0.18)",
    },
    "dramatic": {
        "card": "0 8px 24px rgba(0,0,0,0.2)",
        "hover": "0 16px 48px rgba(0,0,0,0.28)",
    },
}

_SYSTEM_FONT_STACK: Final[str] = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
)

# Dangerous CSS patterns — stripped from any attribute value that reaches CSS output, so a
# malicious value cannot inject ``url(...)`` / ``expression(...)`` / ``javascript:`` into
# the generated stylesheet (parity with the Flask original's sanitiser).
_UNSAFE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(url\s*\(|expression\s*\(|javascript\s*:)", re.IGNORECASE
)


class UnsupportedAttributeError(ValueError):
    """Raised when a settings mapping carries a key outside :data:`SUPPORTED_ATTRIBUTES`.

    Per Req 3.4 the capability rejects the request and produces NO styling. The offending
    key is the client's own key, so it is caller-safe to surface (the edge maps this to a
    422 naming the unsupported attribute — see the spec's Error Handling table).
    """

    def __init__(self, attribute: str):
        self.attribute = attribute
        super().__init__(f"Unsupported look-and-feel attribute: {attribute!r}")


@dataclass(frozen=True)
class PageStyles:
    """Layer-2 styling output for one Page.

    Carries the three CSS pieces Layer 3 (the renderer) needs, mirroring the three outputs
    the Flask ``LandingPageStyles`` produced:

    - :attr:`css_variables` — the ``:root { ... }`` variables block (fonts, spacing,
      radius, shadows), from the former ``build_css_variables``.
    - :attr:`page_css` — the page CSS using those variables + the two brand colours, from
      the former ``build_page_css``.
    - :attr:`font_links` — the Google-Fonts ``<link>`` tags (empty when no web font is
      selected), from the former ``build_font_links``.

    Frozen so a produced value object cannot be mutated by a caller.
    """

    css_variables: str
    page_css: str
    font_links: str


def _sanitize(value: str) -> str:
    """Strip dangerous CSS patterns from a value before it reaches generated CSS."""
    return _UNSAFE_PATTERN.sub("", value)


def _resolve(settings: Mapping[str, Any], attribute: str) -> str:
    """Return the supplied value for ``attribute`` or its SAM-owned default (Req 1.3/3.3).

    An absent key — or a key present with ``None`` — falls back to the default; the result
    is coerced to ``str`` so a caller cannot smuggle a non-string type into the CSS output.
    """
    value = settings.get(attribute)
    if value is None:
        return _DEFAULTS[attribute]
    return str(value)


def _build_css_variables(
    font_heading: str,
    font_body: str,
    base_spacing: str,
    border_radius_global: str,
    shadow_style: str,
    color_primary: str = _DEFAULTS["color_primary"],
    color_accent: str = _DEFAULTS["color_accent"],
) -> str:
    """Build the ``:root`` variables block (relocated from ``build_css_variables``).

    The bugfix ``bugfix-published-form-styling`` (DD-B1) ADDS ``--color-primary`` /
    ``--color-accent`` to the existing font/spacing/radius/shadow variables so the new
    application-form CSS block can reference the two brand colours by variable (the colours
    were previously inlined ONLY into the landing-page rules). The addition is purely
    ADDITIVE: the existing variable lines are emitted unchanged and in order (bugfix 3.4),
    the two colour lines appended just before the closing ``}``.
    """
    lines: list[str] = [":root {"]

    heading_family = (
        f'"{_sanitize(font_heading)}", sans-serif'
        if font_heading.lower() != "system"
        else _SYSTEM_FONT_STACK
    )
    body_family = (
        f'"{_sanitize(font_body)}", sans-serif'
        if font_body.lower() != "system"
        else _SYSTEM_FONT_STACK
    )
    lines.append(f"  --font-heading: {heading_family};")
    lines.append(f"  --font-body: {body_family};")

    spacing = _SPACING_MAP.get(base_spacing, _SPACING_MAP["normal"])
    lines.append(f"  --spacing-section: {spacing['section']};")
    lines.append(f"  --spacing-element: {spacing['element']};")

    radii = _GLOBAL_RADIUS_MAP.get(border_radius_global, _GLOBAL_RADIUS_MAP["rounded"])
    lines.append(f"  --radius-sm: {radii['sm']};")
    lines.append(f"  --radius-md: {radii['md']};")
    lines.append(f"  --radius-lg: {radii['lg']};")

    shadows = _SHADOW_MAP.get(shadow_style, _SHADOW_MAP["subtle"])
    lines.append(f"  --shadow-card: {shadows['card']};")
    lines.append(f"  --shadow-hover: {shadows['hover']};")

    # bugfix DD-B1: the two brand colours as :root variables (sanitised), so the new
    # application-form block below can apply them to the form's OWN elements by variable.
    # Appended AFTER the existing variable lines so the pre-fix variable block survives as
    # an ordered subsequence (preservation guard 3.4).
    lines.append(f"  --color-primary: {_sanitize(color_primary)};")
    lines.append(f"  --color-accent: {_sanitize(color_accent)};")

    lines.append("}")
    return "\n".join(lines)


def _build_font_links(font_heading: str, font_body: str) -> str:
    """Build the Google-Font ``<link>`` tags (relocated from ``build_font_links``).

    Only fonts that are actually selected (not ``system``) load a stylesheet; when neither
    font is a web font the result is the empty string.
    """
    fonts: set[str] = set()
    for font in (font_heading, font_body):
        if font and font.lower() != "system":
            fonts.add(font)

    if not fonts:
        return ""

    families = "&family=".join(
        f.replace(" ", "+") + ":wght@400;600;700" for f in sorted(fonts)
    )
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link href="https://fonts.googleapis.com/css2?family={families}&display=swap" rel="stylesheet">'
    )


def _build_page_css(
    color_primary: str,
    color_accent: str,
    columns: int | str = _DEFAULT_FORM_COLUMNS,
) -> str:
    """Build the page CSS from the two brand colours (relocated from ``build_page_css``).

    Uses the CSS variables defined by :func:`_build_css_variables` (``--font-body`` etc.);
    the LANDING-PAGE colour theming is inlined via the two sanitised brand colours exactly
    as before (unchanged — bugfix 3.7). The bugfix ``bugfix-published-form-styling`` (DD-B1)
    APPENDS an application-form CSS block (:func:`_build_application_form_css`) after all the
    existing rules — it references the ``--color-*`` variables and the ``columns`` track
    count; it does not alter any pre-fix rule. ``columns`` defaults so existing callers (and
    the preservation golden, which calls this with only the two colours) are unaffected.
    """
    color_primary = _sanitize(color_primary)
    color_accent = _sanitize(color_accent)
    return f"""    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: var(--font-body); color: #333; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    .section {{ padding: var(--spacing-section) 1.5rem; }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .hero {{ display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }}
    .hero-text {{ flex: 1; min-width: 280px; }}
    .hero-img {{ flex: 1; min-width: 280px; }}
    .hero h1 {{ font-family: var(--font-heading); font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; color: {color_primary}; }}
    .hero p {{ font-size: 1.2rem; color: #555; margin-bottom: 1rem; }}
    .btn {{ display: inline-block; padding: 0.75rem 1.5rem; background: {color_accent}; color: #fff; text-decoration: none; border-radius: var(--radius-sm); font-weight: 600; }}
    .btn:hover {{ opacity: 0.9; }}
    .about {{ background: #f9f9f9; }}
    .about-content {{ display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }}
    .about-text {{ flex: 1; min-width: 280px; }}
    .about-text h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; }}
    .about-text p {{ margin-bottom: 0.75rem; color: #555; }}
    .about-img {{ flex: 1; min-width: 280px; }}
    .about-img img {{ border-radius: var(--radius-md); }}
    .gallery {{ text-align: center; }}
    .gallery h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .gallery-grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }}
    .gallery-grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }}
    .gallery-masonry {{ columns: 3; column-gap: 1rem; }}
    .gallery-masonry img {{ break-inside: avoid; margin-bottom: 1rem; }}
    .gallery-grid-3 img, .gallery-grid-4 img {{ border-radius: var(--radius-md); width: 100%; height: auto; object-fit: contain; }}
    .gallery-masonry img {{ border-radius: var(--radius-md); width: 100%; height: auto; }}
    .carousel {{ position: relative; overflow: hidden; border-radius: var(--radius-md); max-width: 800px; margin: 0 auto; }}
    .carousel-track {{ display: flex; transition: transform 0.4s ease; }}
    .carousel-slide {{ min-width: 100%; }}
    .carousel-slide img {{ width: 100%; height: auto; max-height: 500px; object-fit: contain; display: block; margin: 0 auto; }}
    .carousel-btn {{ position: absolute; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: #fff; border: none; padding: 0.8rem 1rem; font-size: 1.2rem; cursor: pointer; border-radius: 4px; z-index: 2; }}
    .carousel-btn:hover {{ background: rgba(0,0,0,0.8); }}
    .carousel-prev {{ left: 0.5rem; }}
    .carousel-next {{ right: 0.5rem; }}
    .carousel-dots {{ text-align: center; padding: 0.8rem 0; }}
    .carousel-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #ccc; margin: 0 4px; cursor: pointer; transition: background 0.3s; }}
    .carousel-dot.active {{ background: {color_primary}; }}
    @media (max-width: 768px) {{
      .gallery-grid-3, .gallery-grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
      .gallery-masonry {{ columns: 2; }}
    }}
    @media (max-width: 480px) {{
      .gallery-grid-3, .gallery-grid-4 {{ grid-template-columns: 1fr; }}
      .gallery-masonry {{ columns: 1; }}
    }}
    .cta {{ background: {color_primary}; color: #fff; text-align: center; padding: 4rem 1.5rem; }}
    .cta h2 {{ font-family: var(--font-heading); font-size: 2rem; margin-bottom: 0.5rem; }}
    .cta p {{ font-size: 1.1rem; margin-bottom: 1.5rem; opacity: 0.9; }}
    .cta .btn {{ background: {color_accent}; }}
    .faq {{ background: #f9f9f9; }}
    .faq h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .faq-grid {{ display: grid; grid-template-columns: 1fr; gap: 0 2rem; }}
    @media (min-width: 769px) {{ .faq-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .faq-item {{ border-bottom: 1px solid #ddd; padding: 0.4rem 0; margin: 0; display: block; }}
    .faq-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
    .faq-item summary {{ font-weight: 600; cursor: pointer; font-size: 1.05rem; margin: 0; padding: 0; }}
    .faq-item p {{ margin: 0.2rem 0 0.2rem 0; padding: 0; color: #555; line-height: 1.4; }}
    .faq-item[open] summary {{ margin-bottom: 0; }}
    .testimonials {{ text-align: center; }}
    .testimonials h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .testimonial-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }}
    .testimonial-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: left; box-shadow: var(--shadow-card); }}
    .testimonial-card blockquote {{ font-style: italic; color: #555; margin-bottom: 0.75rem; }}
    .testimonial-card cite {{ font-weight: 600; color: {color_primary}; }}
    .contact {{ background: #f9f9f9; }}
    .contact h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; text-align: center; }}
    .contact form {{ max-width: 500px; margin: 0 auto; }}
    .contact input, .contact textarea {{ width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: var(--radius-sm); font-size: 1rem; }}
    .contact textarea {{ min-height: 120px; resize: vertical; }}
    .contact button {{ width: 100%; padding: 0.75rem; background: {color_accent}; color: #fff; border: none; border-radius: var(--radius-md); font-size: 1rem; font-weight: 600; cursor: pointer; }}
    .embed-block iframe {{ width: 100%; border: none; border-radius: var(--radius-md); }}
    .pricing h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }}
    .pricing-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: center; border: 1px solid #eee; box-shadow: var(--shadow-card); }}
    .pricing-card h3 {{ color: {color_primary}; margin-bottom: 0.5rem; }}
    .pricing-card .price {{ font-size: 1.5rem; font-weight: 700; color: {color_accent}; margin-bottom: 0.5rem; }}
    footer {{ background: #222; color: #ccc; padding: 2rem 1.5rem; text-align: center; font-size: 0.9rem; }}
    footer a {{ color: {color_accent}; text-decoration: none; }}
    @media (max-width: 768px) {{
      .hero h1 {{ font-size: 1.8rem; }}
      .section {{ padding: 1.5rem 1rem; }}
    }}
    .application-form .form-field {{ margin-bottom: 1rem; }}
    .application-form label {{ display: block; font-weight: 600; margin-bottom: 0.25rem; }}
    .application-form input, .application-form select, .application-form textarea {{ width: 100%; padding: 0.6rem; border: 1px solid #ccc; border-radius: var(--radius-sm); font-size: 1rem; }}
    .field-error {{ color: #b42318; font-size: 0.9rem; margin-top: 0.25rem; }}
    .form-field.has-error input, .form-field.has-error select, .form-field.has-error textarea, .form-meta-field.has-error input, .form-meta-field.has-error select {{ border: 1px solid #b42318; outline-color: #b42318; }}
    .form-field.has-error label {{ color: #b42318; }}
    .form-status {{ margin: 1rem 0; min-height: 1.2em; }}
    .form-status-error {{ color: #b42318; font-weight: 600; }}
    .form-status-success {{ color: #027a48; font-weight: 600; }}
{_build_application_form_css(color_primary, color_accent, columns)}"""


def _build_application_form_css(
    color_primary: str, color_accent: str, columns: int | str
) -> str:
    """Build the application-form CSS block (bugfix ``bugfix-published-form-styling`` DD-B1).

    This is the ADDITIVE block that makes the PUBLISHED form genuinely carry the tenant's
    look-and-feel on the form's OWN elements — the fix for the spec-15 defect where the
    look-and-feel only ever themed landing-page classes the form markup never uses.

    It is emitted AFTER the whole existing page CSS (landing-page rules + the original
    ``.application-form`` field/label/error rules), so every pre-fix rule survives
    byte-identical and in order — the key Option-1 regression guard (bugfix 3.7, pinned by
    ``test_published_form_styling_preservation_props``). Nothing above this block is touched.

    What it adds, referencing the ``--color-primary`` / ``--color-accent`` ``:root``
    variables introduced in :func:`_build_css_variables`:

    - **Brand colours on the form's OWN elements** (bugfix 2.1): the visible form heading /
      title (``.application-form h1`` / ``.application-form .form-title`` — the renderer,
      Task 6.1, emits a visible heading element), the submit ``<button type="submit">``, and
      the input / select / textarea ``:focus`` state. A colour change is now observable on
      the form itself, not only on unused landing classes. The resolved brand colour is
      inlined DIRECTLY into these form rules (mirroring how the landing rules inline their
      colours) so the colour genuinely reaches the form's own elements — and is traceable to
      them — rather than hiding behind a variable the artifact never resolves at test time.
      The matching ``--color-primary`` / ``--color-accent`` ``:root`` variables (DD-B1) are
      ALSO emitted (see :func:`_build_css_variables`) so the one SAM-owned style source
      exposes the brand colours as variables for the preview path to read (design §E).
    - **A multi-column, collapsing grid** (bugfix 2.2): the field containers inside each
      ``.form-group`` are laid out in a grid of ``columns`` tracks, collapsing to a single
      column below the small-screen breakpoint — mirroring the existing
      ``@media (max-width: 480px)`` single-column collapse the landing-page gallery grids use.
      ``columns`` is driven later by the new ``columns`` attribute (Task 8); for now a
      sensible multi-column default applies.

    Args:
        color_primary: the resolved, already-sanitised primary brand colour — inlined into
            the form heading / submit / focus rules (and also exposed as ``--color-primary``).
        color_accent: the resolved, already-sanitised accent brand colour — inlined into the
            submit-button hover (and also exposed as ``--color-accent``).
        columns: the number of layout columns for the form's field groups (clamped to a
            sane 1..4 range; a single column emits the collapsing grid as a no-op so the
            markup/behaviour stays consistent).

    Returns:
        The application-form CSS block (indented to match the surrounding page CSS), with a
        leading newline-free join handled by the caller's f-string.
    """
    # Clamp to a sane range so a stray/out-of-range value can never emit a broken track list
    # (the authoritative validation lives at the edge/service plane — Task 10 — this is a
    # defensive floor/ceiling so the generator always emits well-formed CSS).
    try:
        track_count = int(columns)
    except (TypeError, ValueError):
        track_count = _DEFAULT_FORM_COLUMNS
    track_count = max(1, min(track_count, _MAX_FORM_COLUMNS))

    return f"""    .application-form h1, .application-form .form-title {{ font-family: var(--font-heading); color: {color_primary}; margin-bottom: var(--spacing-element); }}
    .application-form h2 {{ font-family: var(--font-heading); color: {color_primary}; margin-bottom: var(--spacing-element); }}
    .application-form .form-logo {{ max-height: 96px; width: auto; margin-bottom: var(--spacing-element); }}
    .application-form .form-group {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: var(--spacing-element); border: none; margin-bottom: var(--spacing-section); max-width: calc({track_count} * 20rem + ({track_count} - 1) * var(--spacing-element)); }}
    .application-form .form-group[data-group="_meta"] {{ grid-template-columns: 1fr; }}
    .application-form .form-group > h2 {{ grid-column: 1 / -1; }}
    .application-form input:focus, .application-form select:focus, .application-form textarea:focus {{ outline: 2px solid {color_primary}; outline-offset: 1px; border-color: {color_primary}; }}
    .application-form button[type="submit"] {{ background: {color_primary}; color: #fff; border: none; padding: 0.75rem 1.5rem; border-radius: var(--radius-sm); font-size: 1rem; font-weight: 600; cursor: pointer; }}
    .application-form button[type="submit"]:hover {{ background: {color_accent}; }}"""


def render_page_styles(settings: Mapping[str, Any]) -> PageStyles:
    """Layer 2 (C1): produce a Page's styling output from its Look_And_Feel_Settings values.

    Pure and deterministic — identical ``settings`` produce identical output (Req 1.2/1.5).
    Page-type-agnostic — reads ONLY the supplied values mapping, holds no page-specific
    state (Req 6.3), so the Application_Form (today) and a future Landing_Page (Req 6) call
    this SAME function.

    Args:
        settings: the Page's Look_And_Feel_Settings VALUES. Recognised keys are exactly the
            ten in :data:`SUPPORTED_ATTRIBUTES` (the original seven plus ``columns`` /
            ``logo`` / ``header_title``). An absent (or ``None``) attribute falls back to its
            SAM-owned default (Req 1.3/3.3/4.4/5.4). ``columns`` drives the application-form
            grid; ``logo`` / ``header_title`` are carried for the renderer and emit no CSS.

    Returns:
        A :class:`PageStyles` carrying the ``:root`` variables block, the page CSS, and the
        font ``<link>`` tags.

    Raises:
        UnsupportedAttributeError: if ``settings`` carries any key outside
            :data:`SUPPORTED_ATTRIBUTES`. The request is rejected and NO styling is
            produced (Req 3.4).
    """
    # Reject BEFORE producing any styling (Req 3.4): an unsupported key fails the whole
    # request so no partial styling escapes. Sorted so the reported key is deterministic.
    for key in sorted(settings):
        if key not in SUPPORTED_ATTRIBUTES:
            raise UnsupportedAttributeError(key)

    color_primary = _resolve(settings, "color_primary")
    color_accent = _resolve(settings, "color_accent")
    font_heading = _resolve(settings, "font_heading")
    font_body = _resolve(settings, "font_body")
    base_spacing = _resolve(settings, "base_spacing")
    border_radius_global = _resolve(settings, "border_radius_global")
    shadow_style = _resolve(settings, "shadow_style")
    # bugfix bugfix-published-form-styling (Task 8): resolve the authored `columns` value and
    # thread it into the application-form grid. An unset/None value resolves to the
    # multi-column default (via `_DEFAULTS["columns"]`), so the generated CSS is unchanged for
    # a tenant that never authored columns (preservation 3.4). `_build_application_form_css`
    # clamps the value defensively; `logo` / `header_title` are SUPPORTED values the renderer
    # consumes (Task 6) and are intentionally NOT read here — they emit no CSS.
    columns = _resolve(settings, "columns")

    return PageStyles(
        css_variables=_build_css_variables(
            font_heading=font_heading,
            font_body=font_body,
            base_spacing=base_spacing,
            border_radius_global=border_radius_global,
            shadow_style=shadow_style,
            color_primary=color_primary,
            color_accent=color_accent,
        ),
        page_css=_build_page_css(color_primary, color_accent, columns),
        font_links=_build_font_links(font_heading, font_body),
    )
