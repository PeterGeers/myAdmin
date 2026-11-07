/**
 * TS Layer-2 CSS generator — the browser-side `Styling_Logic` for the admin live preview
 * (spec 15 — SAM Page Look-and-Feel, task 13.1; DD-3 option 1, design §C5).
 *
 * This is the React (preview-path) MIRROR of the SAM-owned Python Layer-2 generator
 * `sam/shared/page_styles/__init__.py` (`render_page_styles`). The feature keeps TWO
 * deliberate render paths (design §"The two render paths share the same three layers"):
 *
 *  - the PUBLISHED static form runs the PYTHON Layer-2 generator at publish time, and
 *  - the ADMIN PREVIEW runs THIS in-browser TS equivalent so the admin's UNSAVED edits
 *    appear instantly with no server round-trip (a React component cannot execute the
 *    Python server-side logic).
 *
 * Req 7 parity is therefore *same values → same appearance across the two Layer-2
 * implementations*, NOT one shared renderer. This module reproduces the Python module's
 * output EXACTLY for the same seven supported attributes and the same defaults:
 *
 *  - the same seven {@link SUPPORTED_ATTRIBUTES},
 *  - the same SAM-owned {@link DEFAULTS},
 *  - the same enum lookup maps (`_SPACING_MAP` / `_GLOBAL_RADIUS_MAP` / `_SHADOW_MAP`),
 *  - the same `:root { … }` css-variables block, page CSS, and font `<link>` shape, and
 *  - the same dangerous-pattern sanitiser.
 *
 * Task 13.2 (a LATER wave) pins this TS output to the Python output via a shared parity
 * fixture — this module must produce byte-identical `cssVariables` / `pageCss` /
 * `fontLinks` strings for the same values so that pin holds. Do NOT reformat the generated
 * CSS without changing the Python side in lockstep.
 *
 * Pure + deterministic: identical `settings` → identical output. Page-type-agnostic: reads
 * ONLY the supplied values; holds no page-specific state.
 */

/**
 * The supported attributes — now TEN — mirrors the Python `SUPPORTED_ATTRIBUTES` frozenset.
 * A key outside this set is unsupported and causes {@link renderPageStyles} to reject the
 * request (Req 3.4).
 *
 * The first SEVEN are the original spec-15 contract (colours / fonts / spacing / radius /
 * shadow). The bugfix `bugfix-published-form-styling` (Req 2.2 / 2.7, design §C) extends the
 * set with THREE new values-only attributes — a deliberate, DOCUMENTED extension of the
 * exactly-seven set (bugfix 3.4):
 *
 *  - `columns`      — the number of layout columns for the form's field groups; DRIVES the
 *                     application-form grid `grid-template-columns` track count (clamped 1..4
 *                     here, mirroring the Python generator — the authoritative out-of-range
 *                     rejection lives at the edge/service plane).
 *  - `logo`         — a URL/asset reference to the tenant logo; CARRIED as a supported value
 *                     but NOT emitted as CSS — the renderer/preview consumes it.
 *  - `header_title` — the form header/title text; likewise CARRIED for the renderer/preview,
 *                     not emitted as CSS.
 *
 * `logo` / `header_title` are accepted so {@link renderPageStyles} does not reject them as
 * unsupported, but they produce NO CSS of their own. `columns` is the only new attribute that
 * affects the generated CSS. Any key OUTSIDE these ten is still rejected (Req 3.4).
 */
export const SUPPORTED_ATTRIBUTES = [
  'color_primary',
  'color_accent',
  'font_heading',
  'font_body',
  'base_spacing',
  'border_radius_global',
  'shadow_style',
  // bugfix bugfix-published-form-styling (Req 2.2 / 2.7) — the three new values-only
  // attributes; a documented extension of the original seven (bugfix 3.4).
  'columns',
  'logo',
  'header_title',
] as const;

export type SupportedAttribute = (typeof SUPPORTED_ATTRIBUTES)[number];

const SUPPORTED_SET: ReadonlySet<string> = new Set(SUPPORTED_ATTRIBUTES);

/**
 * Default / ceiling for the application-form multi-column grid (bugfix DD-B1) — mirrors the
 * Python `_DEFAULT_FORM_COLUMNS` / `_MAX_FORM_COLUMNS`. The `columns` attribute drives the
 * grid track count; an unset value falls back to the default, and the generator clamps to a
 * sane 1..4 range so a stray value never emits a broken track list (the authoritative
 * out-of-range rejection lives at the edge/service plane).
 */
const DEFAULT_FORM_COLUMNS = 2;
const MAX_FORM_COLUMNS = 4;

/**
 * SAM-owned defaults (Req 1.3, 3.3) — mirrors the Python `_DEFAULTS` map EXACTLY. A missing
 * (or `null`/`undefined`) attribute resolves to the default below.
 *
 * The three bugfix attributes default so a tenant that never authored them renders exactly as
 * today: `columns` to the sensible multi-column count the form grid already used, and `logo` /
 * `header_title` to EMPTY (no logo / no heading — the renderer treats an empty value as
 * "absent").
 */
export const DEFAULTS: Readonly<Record<SupportedAttribute, string>> = {
  color_primary: '#2D5F8A',
  color_accent: '#F4A261',
  font_heading: 'system',
  font_body: 'system',
  base_spacing: 'normal',
  border_radius_global: 'rounded',
  shadow_style: 'subtle',
  // bugfix bugfix-published-form-styling (Req 2.2 / 2.7 / 3.3) — defaults for the three new
  // attributes; mirrors the Python `_DEFAULTS`.
  columns: String(DEFAULT_FORM_COLUMNS),
  logo: '',
  header_title: '',
};

/** Spacing enum map — mirrors the Python `_SPACING_MAP`. */
const SPACING_MAP: Readonly<Record<string, { section: string; element: string }>> = {
  compact: { section: '1.5rem', element: '0.75rem' },
  normal: { section: '2rem', element: '1rem' },
  relaxed: { section: '3rem', element: '1.5rem' },
};

/** Global-radius enum map — mirrors the Python `_GLOBAL_RADIUS_MAP`. */
const GLOBAL_RADIUS_MAP: Readonly<Record<string, { sm: string; md: string; lg: string }>> = {
  sharp: { sm: '0', md: '0', lg: '0' },
  rounded: { sm: '4px', md: '8px', lg: '16px' },
  pill: { sm: '12px', md: '24px', lg: '9999px' },
};

/** Shadow enum map — mirrors the Python `_SHADOW_MAP`. */
const SHADOW_MAP: Readonly<Record<string, { card: string; hover: string }>> = {
  none: { card: 'none', hover: 'none' },
  subtle: {
    card: '0 2px 8px rgba(0,0,0,0.08)',
    hover: '0 4px 16px rgba(0,0,0,0.12)',
  },
  medium: {
    card: '0 4px 12px rgba(0,0,0,0.12)',
    hover: '0 8px 24px rgba(0,0,0,0.18)',
  },
  dramatic: {
    card: '0 8px 24px rgba(0,0,0,0.2)',
    hover: '0 16px 48px rgba(0,0,0,0.28)',
  },
};

/** The system font stack used when a font attribute is `system` — mirrors `_SYSTEM_FONT_STACK`. */
const SYSTEM_FONT_STACK =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

/**
 * Dangerous CSS patterns stripped from any attribute value before it reaches CSS output, so
 * a malicious value cannot inject `url(...)` / `expression(...)` / `javascript:` into the
 * generated stylesheet — parity with the Python `_UNSAFE_PATTERN` sanitiser. Global +
 * case-insensitive so every occurrence is removed.
 */
const UNSAFE_PATTERN = /(url\s*\(|expression\s*\(|javascript\s*:)/gi;

/**
 * Raised when a settings mapping carries a key outside {@link SUPPORTED_ATTRIBUTES}. Per
 * Req 3.4 the capability rejects the request and produces NO styling. Mirrors the Python
 * `UnsupportedAttributeError`.
 */
export class UnsupportedAttributeError extends Error {
  readonly attribute: string;

  constructor(attribute: string) {
    super(`Unsupported look-and-feel attribute: ${JSON.stringify(attribute)}`);
    this.name = 'UnsupportedAttributeError';
    this.attribute = attribute;
  }
}

/**
 * Layer-2 styling output for one Page — mirrors the Python `PageStyles` dataclass. Carries
 * the three CSS pieces Layer 3 (the renderer) needs: the `:root` variables block, the page
 * CSS, and the font `<link>` tags (empty when no web font is selected).
 */
export interface PageStyles {
  /** The `:root { … }` variables block (fonts, spacing, radius, shadows). */
  readonly cssVariables: string;
  /**
   * The SAME custom properties as {@link cssVariables}, as a property-name → value map (e.g.
   * `{ '--font-heading': '…', '--spacing-section': '2rem', … }`). Not part of the Python
   * `PageStyles` (the Python renderer injects the `:root` string); it exists on the React
   * side so the preview can apply the variables to its container scope as a style object. It
   * is derived from the same values as {@link cssVariables} so the two cannot drift.
   */
  readonly cssVariableMap: Readonly<Record<string, string>>;
  /** The page CSS using those variables + the two brand colours. */
  readonly pageCss: string;
  /** The Google-Fonts `<link>` tags (empty string when no web font is selected). */
  readonly fontLinks: string;
}

/** The input values mapping — recognised keys are the seven supported attributes. */
export type LookAndFeelSettings = Partial<Record<SupportedAttribute, unknown>> &
  Record<string, unknown>;

/** Strip dangerous CSS patterns from a value before it reaches generated CSS. */
function sanitize(value: string): string {
  return value.replace(UNSAFE_PATTERN, '');
}

/**
 * Return the supplied value for `attribute` or its SAM-owned default (Req 1.3/3.3). An
 * absent key — or a key present with `null`/`undefined` — falls back to the default; the
 * result is coerced to a string so a caller cannot smuggle a non-string type into the CSS.
 */
function resolve(settings: LookAndFeelSettings, attribute: SupportedAttribute): string {
  const value = settings[attribute];
  if (value === undefined || value === null) {
    return DEFAULTS[attribute];
  }
  return String(value);
}

/**
 * Resolve the `:root` custom properties as an ordered key→value map (CSS property name →
 * value). The {@link buildCssVariables} string is built from this SAME map, so the two can
 * never drift. The React preview consumes this map directly to apply the variables to the
 * preview container's scope (a `{ '--font-heading': … }` style object), while the parity
 * fixture (task 13.2) consumes the string form.
 */
function resolveCssVariableEntries(
  fontHeading: string,
  fontBody: string,
  baseSpacing: string,
  borderRadiusGlobal: string,
  shadowStyle: string,
  colorPrimary: string,
  colorAccent: string,
): Array<[string, string]> {
  const headingFamily =
    fontHeading.toLowerCase() !== 'system'
      ? `"${sanitize(fontHeading)}", sans-serif`
      : SYSTEM_FONT_STACK;
  const bodyFamily =
    fontBody.toLowerCase() !== 'system'
      ? `"${sanitize(fontBody)}", sans-serif`
      : SYSTEM_FONT_STACK;

  const spacing = SPACING_MAP[baseSpacing] ?? SPACING_MAP.normal;
  const radii = GLOBAL_RADIUS_MAP[borderRadiusGlobal] ?? GLOBAL_RADIUS_MAP.rounded;
  const shadows = SHADOW_MAP[shadowStyle] ?? SHADOW_MAP.subtle;

  return [
    ['--font-heading', headingFamily],
    ['--font-body', bodyFamily],
    ['--spacing-section', spacing.section],
    ['--spacing-element', spacing.element],
    ['--radius-sm', radii.sm],
    ['--radius-md', radii.md],
    ['--radius-lg', radii.lg],
    ['--shadow-card', shadows.card],
    ['--shadow-hover', shadows.hover],
    // bugfix DD-B1: the two brand colours as :root variables (sanitised), appended AFTER the
    // existing variable lines so the pre-fix block survives as an ordered subsequence — the
    // new application-form block applies them to the form's OWN elements. Mirrors the Python
    // `_build_css_variables`.
    ['--color-primary', sanitize(colorPrimary)],
    ['--color-accent', sanitize(colorAccent)],
  ];
}

/**
 * Build the `:root` variables block — mirrors the Python `_build_css_variables`. Built from
 * {@link resolveCssVariableEntries} so the string and the {@link PageStyles.cssVariableMap}
 * object are always in lockstep.
 */
function buildCssVariables(entries: Array<[string, string]>): string {
  const lines: string[] = [':root {'];
  for (const [name, value] of entries) {
    lines.push(`  ${name}: ${value};`);
  }
  lines.push('}');
  return lines.join('\n');
}

/**
 * Build the Google-Font `<link>` tags — mirrors the Python `_build_font_links`. Only fonts
 * that are actually selected (not `system`) load a stylesheet; when neither font is a web
 * font the result is the empty string. Families are sorted so output is deterministic.
 */
function buildFontLinks(fontHeading: string, fontBody: string): string {
  const fonts = new Set<string>();
  for (const font of [fontHeading, fontBody]) {
    if (font && font.toLowerCase() !== 'system') {
      fonts.add(font);
    }
  }

  if (fonts.size === 0) {
    return '';
  }

  const families = [...fonts]
    .sort()
    .map((f) => `${f.replace(/ /g, '+')}:wght@400;600;700`)
    .join('&family=');
  return (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n' +
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n' +
    `<link href="https://fonts.googleapis.com/css2?family=${families}&display=swap" rel="stylesheet">`
  );
}

/**
 * Build the page CSS from the two brand colours — mirrors the Python `_build_page_css`.
 * Uses the CSS variables defined by {@link buildCssVariables}; colour theming is inlined via
 * the two sanitised brand colours.
 *
 * NOTE: this string must stay byte-identical to the Python `_build_page_css` output for the
 * same colours (task 13.2 parity fixture). Keep the leading indentation and line order
 * exactly as the Python side emits them.
 */
function buildPageCss(
  colorPrimaryRaw: string,
  colorAccentRaw: string,
  columns: number | string = DEFAULT_FORM_COLUMNS,
): string {
  const colorPrimary = sanitize(colorPrimaryRaw);
  const colorAccent = sanitize(colorAccentRaw);
  return `    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--font-body); color: #333; line-height: 1.6; }
    img { max-width: 100%; height: auto; display: block; }
    .section { padding: var(--spacing-section) 1.5rem; }
    .container { max-width: 1100px; margin: 0 auto; }
    .hero { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }
    .hero-text { flex: 1; min-width: 280px; }
    .hero-img { flex: 1; min-width: 280px; }
    .hero h1 { font-family: var(--font-heading); font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; color: ${colorPrimary}; }
    .hero p { font-size: 1.2rem; color: #555; margin-bottom: 1rem; }
    .btn { display: inline-block; padding: 0.75rem 1.5rem; background: ${colorAccent}; color: #fff; text-decoration: none; border-radius: var(--radius-sm); font-weight: 600; }
    .btn:hover { opacity: 0.9; }
    .about { background: #f9f9f9; }
    .about-content { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }
    .about-text { flex: 1; min-width: 280px; }
    .about-text h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: ${colorPrimary}; }
    .about-text p { margin-bottom: 0.75rem; color: #555; }
    .about-img { flex: 1; min-width: 280px; }
    .about-img img { border-radius: var(--radius-md); }
    .gallery { text-align: center; }
    .gallery h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: ${colorPrimary}; }
    .gallery-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
    .gallery-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
    .gallery-masonry { columns: 3; column-gap: 1rem; }
    .gallery-masonry img { break-inside: avoid; margin-bottom: 1rem; }
    .gallery-grid-3 img, .gallery-grid-4 img { border-radius: var(--radius-md); width: 100%; height: auto; object-fit: contain; }
    .gallery-masonry img { border-radius: var(--radius-md); width: 100%; height: auto; }
    .carousel { position: relative; overflow: hidden; border-radius: var(--radius-md); max-width: 800px; margin: 0 auto; }
    .carousel-track { display: flex; transition: transform 0.4s ease; }
    .carousel-slide { min-width: 100%; }
    .carousel-slide img { width: 100%; height: auto; max-height: 500px; object-fit: contain; display: block; margin: 0 auto; }
    .carousel-btn { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: #fff; border: none; padding: 0.8rem 1rem; font-size: 1.2rem; cursor: pointer; border-radius: 4px; z-index: 2; }
    .carousel-btn:hover { background: rgba(0,0,0,0.8); }
    .carousel-prev { left: 0.5rem; }
    .carousel-next { right: 0.5rem; }
    .carousel-dots { text-align: center; padding: 0.8rem 0; }
    .carousel-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #ccc; margin: 0 4px; cursor: pointer; transition: background 0.3s; }
    .carousel-dot.active { background: ${colorPrimary}; }
    @media (max-width: 768px) {
      .gallery-grid-3, .gallery-grid-4 { grid-template-columns: repeat(2, 1fr); }
      .gallery-masonry { columns: 2; }
    }
    @media (max-width: 480px) {
      .gallery-grid-3, .gallery-grid-4 { grid-template-columns: 1fr; }
      .gallery-masonry { columns: 1; }
    }
    .cta { background: ${colorPrimary}; color: #fff; text-align: center; padding: 4rem 1.5rem; }
    .cta h2 { font-family: var(--font-heading); font-size: 2rem; margin-bottom: 0.5rem; }
    .cta p { font-size: 1.1rem; margin-bottom: 1.5rem; opacity: 0.9; }
    .cta .btn { background: ${colorAccent}; }
    .faq { background: #f9f9f9; }
    .faq h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: ${colorPrimary}; text-align: center; }
    .faq-grid { display: grid; grid-template-columns: 1fr; gap: 0 2rem; }
    @media (min-width: 769px) { .faq-grid { grid-template-columns: repeat(2, 1fr); } }
    .faq-item { border-bottom: 1px solid #ddd; padding: 0.4rem 0; margin: 0; display: block; }
    .faq-item:last-child { border-bottom: none; padding-bottom: 0; }
    .faq-item summary { font-weight: 600; cursor: pointer; font-size: 1.05rem; margin: 0; padding: 0; }
    .faq-item p { margin: 0.2rem 0 0.2rem 0; padding: 0; color: #555; line-height: 1.4; }
    .faq-item[open] summary { margin-bottom: 0; }
    .testimonials { text-align: center; }
    .testimonials h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: ${colorPrimary}; }
    .testimonial-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }
    .testimonial-card { background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: left; box-shadow: var(--shadow-card); }
    .testimonial-card blockquote { font-style: italic; color: #555; margin-bottom: 0.75rem; }
    .testimonial-card cite { font-weight: 600; color: ${colorPrimary}; }
    .contact { background: #f9f9f9; }
    .contact h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: ${colorPrimary}; text-align: center; }
    .contact form { max-width: 500px; margin: 0 auto; }
    .contact input, .contact textarea { width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: var(--radius-sm); font-size: 1rem; }
    .contact textarea { min-height: 120px; resize: vertical; }
    .contact button { width: 100%; padding: 0.75rem; background: ${colorAccent}; color: #fff; border: none; border-radius: var(--radius-md); font-size: 1rem; font-weight: 600; cursor: pointer; }
    .embed-block iframe { width: 100%; border: none; border-radius: var(--radius-md); }
    .pricing h2 { font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: ${colorPrimary}; text-align: center; }
    .pricing-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }
    .pricing-card { background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: center; border: 1px solid #eee; box-shadow: var(--shadow-card); }
    .pricing-card h3 { color: ${colorPrimary}; margin-bottom: 0.5rem; }
    .pricing-card .price { font-size: 1.5rem; font-weight: 700; color: ${colorAccent}; margin-bottom: 0.5rem; }
    footer { background: #222; color: #ccc; padding: 2rem 1.5rem; text-align: center; font-size: 0.9rem; }
    footer a { color: ${colorAccent}; text-decoration: none; }
    @media (max-width: 768px) {
      .hero h1 { font-size: 1.8rem; }
      .section { padding: 1.5rem 1rem; }
    }
    .application-form .form-field { margin-bottom: 1rem; }
    .application-form label { display: block; font-weight: 600; margin-bottom: 0.25rem; }
    .application-form input, .application-form select, .application-form textarea { width: 100%; padding: 0.6rem; border: 1px solid #ccc; border-radius: var(--radius-sm); font-size: 1rem; }
    .field-error { color: #b42318; font-size: 0.9rem; margin-top: 0.25rem; }
    .form-field.has-error input, .form-field.has-error select, .form-field.has-error textarea, .form-meta-field.has-error input, .form-meta-field.has-error select { border: 1px solid #b42318; outline-color: #b42318; }
    .form-field.has-error label { color: #b42318; }
    .form-status { margin: 1rem 0; min-height: 1.2em; }
    .form-status-error { color: #b42318; font-weight: 600; }
    .form-status-success { color: #027a48; font-weight: 600; }
${buildApplicationFormCss(colorPrimary, colorAccent, columns)}`;
}

/**
 * Build the application-form CSS block — mirrors the Python `_build_application_form_css`
 * (bugfix `bugfix-published-form-styling` DD-B1). This is the ADDITIVE block that makes the
 * form genuinely carry the tenant's look-and-feel on the form's OWN elements:
 *
 *  - brand colours on the form heading/title, the submit button (+ accent hover), and the
 *    input/select/textarea `:focus` state (bugfix 2.1), and
 *  - a multi-column grid driven by `columns` that collapses to a single column below the
 *    small-screen breakpoint (bugfix 2.2).
 *
 * The resolved brand colours are inlined DIRECTLY into these rules (not referenced via the
 * `--color-*` variables) so the parity output byte-matches the Python side, where the colour
 * is inlined into the form rules too. Keep the leading indentation and line order exactly as
 * the Python `_build_application_form_css` emits them (task 13.2 parity fixture).
 */
function buildApplicationFormCss(
  colorPrimary: string,
  colorAccent: string,
  columns: number | string,
): string {
  // Clamp to a sane range so a stray/out-of-range value can never emit a broken track list —
  // mirrors the Python defensive floor/ceiling (the authoritative validation is at the
  // edge/service plane). A non-numeric value falls back to the default.
  let trackCount = Number.parseInt(String(columns), 10);
  if (Number.isNaN(trackCount)) {
    trackCount = DEFAULT_FORM_COLUMNS;
  }
  trackCount = Math.max(1, Math.min(trackCount, MAX_FORM_COLUMNS));

  return `    .application-form h1, .application-form .form-title { font-family: var(--font-heading); color: ${colorPrimary}; margin-bottom: var(--spacing-element); }
    .application-form h2 { font-family: var(--font-heading); color: ${colorPrimary}; margin-bottom: var(--spacing-element); }
    .application-form .form-logo { max-height: 96px; width: auto; margin-bottom: var(--spacing-element); }
    .application-form .form-group { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: var(--spacing-element); border: none; margin-bottom: var(--spacing-section); max-width: calc(${trackCount} * 20rem + (${trackCount} - 1) * var(--spacing-element)); }
    .application-form .form-group[data-group="_meta"] { grid-template-columns: 1fr; }
    .application-form .form-group > h2 { grid-column: 1 / -1; }
    .application-form input:focus, .application-form select:focus, .application-form textarea:focus { outline: 2px solid ${colorPrimary}; outline-offset: 1px; border-color: ${colorPrimary}; }
    .application-form button[type="submit"] { background: ${colorPrimary}; color: #fff; border: none; padding: 0.75rem 1.5rem; border-radius: var(--radius-sm); font-size: 1rem; font-weight: 600; cursor: pointer; }
    .application-form button[type="submit"]:hover { background: ${colorAccent}; }`;
}

/**
 * Layer 2 (C1, React mirror): produce a Page's styling output from its
 * `Look_And_Feel_Settings` values — the TS equivalent of the Python `render_page_styles`.
 *
 * Pure and deterministic — identical `settings` produce identical output (Req 1.2/1.5).
 * Page-type-agnostic — reads ONLY the supplied values mapping, holds no page-specific state
 * (Req 6.3). An absent (or `null`/`undefined`) attribute falls back to its SAM-owned default
 * (Req 1.3/3.3/4.4/5.4).
 *
 * @throws {UnsupportedAttributeError} if `settings` carries any key outside
 *   {@link SUPPORTED_ATTRIBUTES}. The request is rejected and NO styling is produced
 *   (Req 3.4). Keys are checked in sorted order so the reported key is deterministic —
 *   mirroring the Python `sorted(settings)` rejection order.
 */
export function renderPageStyles(settings: LookAndFeelSettings): PageStyles {
  // Reject BEFORE producing any styling (Req 3.4): an unsupported key fails the whole
  // request so no partial styling escapes. Sorted so the reported key is deterministic
  // (parity with the Python `for key in sorted(settings)`).
  for (const key of Object.keys(settings).sort()) {
    if (!SUPPORTED_SET.has(key)) {
      throw new UnsupportedAttributeError(key);
    }
  }

  const colorPrimary = resolve(settings, 'color_primary');
  const colorAccent = resolve(settings, 'color_accent');
  const fontHeading = resolve(settings, 'font_heading');
  const fontBody = resolve(settings, 'font_body');
  const baseSpacing = resolve(settings, 'base_spacing');
  const borderRadiusGlobal = resolve(settings, 'border_radius_global');
  const shadowStyle = resolve(settings, 'shadow_style');
  // bugfix bugfix-published-form-styling: resolve the authored `columns` value and thread it
  // into the application-form grid. An unset value resolves to the multi-column default, so
  // the generated CSS is unchanged for a tenant that never authored columns (preservation).
  // `buildApplicationFormCss` clamps defensively; `logo` / `header_title` are SUPPORTED values
  // the renderer/preview consumes and are intentionally NOT read here — they emit no CSS.
  const columns = resolve(settings, 'columns');

  const varEntries = resolveCssVariableEntries(
    fontHeading,
    fontBody,
    baseSpacing,
    borderRadiusGlobal,
    shadowStyle,
    colorPrimary,
    colorAccent,
  );

  return {
    cssVariables: buildCssVariables(varEntries),
    cssVariableMap: Object.fromEntries(varEntries),
    pageCss: buildPageCss(colorPrimary, colorAccent, columns),
    fontLinks: buildFontLinks(fontHeading, fontBody),
  };
}
