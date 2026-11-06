/**
 * Frontend/PREVIEW half of the APPLIED-APPEARANCE parity pin across the two render paths
 * (bugfix `bugfix-published-form-styling` Phase 5 / Task 20).
 *
 * Two render paths are retained DELIBERATELY (design §E): the in-browser React preview
 * (immediate, no round-trip) and the published Python-rendered HTML. There is NO single
 * renderer and NO iframe. The fix is that BOTH derive the form's appearance from the SAME
 * resolved `Look_And_Feel_Settings` attributes + SAME defaults, and this parity pin asserts
 * the SAME APPLIED APPEARANCE on each path.
 *
 * This file is the PREVIEW half. Its SAM twin,
 * `sam/tests/test_published_form_applied_styling_parity.py`, publishes with the SAME
 * attributes and asserts the baked HTML applies the styling. Both halves read ONE shared
 * attribute fixture (`applied_appearance_parity.json`), so they provably use the same input —
 * the `fixture copies are byte-identical` drift guard (below, mirrored on the SAM side) pins
 * that the two fixture copies cannot diverge.
 *
 * Why this is NOT the spec-15 task-13.2 string fixture
 * ----------------------------------------------------
 * The spec-15 parity fixture (`page_styles_parity.json` / `pageStyles.parity.test.ts`) only
 * pins that the two Layer-2 GENERATORS emit the same `pageCss` / `cssVariables` STRING. That
 * is INSUFFICIENT and is part of this bug (design §E): the generator string can match
 * byte-for-byte while the FORM is still unstyled, because the string themed only landing-page
 * classes the form markup never used. So this test asserts the APPLIED RESULT on the preview —
 * the tenant logo renders as an `<img>`, the header title renders as a visible heading, and the
 * `columns` value drives the field-group grid track count — and that the styling the preview
 * applies to the form's OWN elements (heading/submit/focus) carries the brand colour. It NEVER
 * merely compares the two generators' strings.
 *
 * Applied-colour predicate
 * ------------------------
 * The preview applies the form's colour styling via the SAME Layer-2 `pageCss` the publish
 * path bakes (the TS `renderPageStyles` mirror of the Python generator). So "the brand colour
 * reaches the form's own elements on the preview path" is asserted with the SAME applied-colour
 * predicate the SAM test uses (a CSS rule that both targets a `.application-form` own element
 * AND carries the colour) — run over the page CSS the preview actually consumes, so it is an
 * applied-result check, not a string-equality compare.
 *
 * Validates: Requirements 2.6; spec-15 Req 7.1 (admin preview reflects published)
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '../../../../test-utils';
import { ApplicationFormPreview } from '../ApplicationFormPreview';
import { renderPageStyles, DEFAULTS, type LookAndFeelSettings } from '../pageStyles';
import type { FieldConfig, FieldConfigField } from '../../../../types/members';

// ── the ONE shared attribute fixture + its canonical SAM twin ─────────────────────────

const _here = dirname(fileURLToPath(import.meta.url));
const FRONTEND_FIXTURE = resolve(_here, 'fixtures/applied_appearance_parity.json');
// _here = frontend/src/components/TenantAdmin/MembersConfig/__tests__ → up 6 to the repo root.
const REPO_ROOT = resolve(_here, '../../../../../..');
const SAM_FIXTURE = resolve(REPO_ROOT, 'sam/tests/fixtures/applied_appearance_parity.json');

interface ParityCase {
  name: string;
  description: string;
  input: {
    color_primary: string;
    color_accent: string;
    columns: string;
    logo: string;
    header_title: string;
  };
}
interface ParityFixture {
  default_primary: string;
  cases: ParityCase[];
}

const FIXTURE = JSON.parse(readFileSync(FRONTEND_FIXTURE, 'utf-8')) as ParityFixture;
const CASES = FIXTURE.cases;
const DEFAULT_PRIMARY = FIXTURE.default_primary;

// ── a minimal on-form config so the preview renders the form (not the empty state) ───

function field(key: string, group: string, extra: Partial<FieldConfigField> = {}): FieldConfigField {
  return {
    key,
    group,
    type: 'string',
    label: { nl: `NL ${key}`, en: `Label ${key}` },
    functional_group: group,
    origin: 'fixed',
    provenance: 'base',
    application_visible: true,
    ...extra,
  };
}
function onFormConfig(): FieldConfig {
  return {
    fields: [
      field('first_name', 'personal'),
      field('last_name', 'personal'),
      field('email', 'contact'),
      field('iban', 'contact'),
    ],
  } as FieldConfig;
}

// ── applied-colour predicate — the SAME notion the SAM published-artifact test uses ───

/** The form's OWN-element selectors that carrying the brand colour means "applied to the form". */
const OWN_ELEMENT_SELECTORS = [
  '.application-form button',
  'button[type="submit"]',
  '.application-form h1',
  '.application-form h2',
  '.application-form .form-title',
  '.application-form input:focus',
  '.application-form select:focus',
  '.application-form textarea:focus',
  '.application-form :focus',
];

/**
 * True when `pageCss` carries `colorPrimary` INSIDE a rule that targets one of the form's own
 * elements — i.e. the brand colour is APPLIED to the form itself, not merely present somewhere
 * in the stylesheet (which is what the string fixture could not distinguish). Mirrors the
 * Python `_applies_brand_colour_to_form` predicate.
 */
function appliesBrandColourToForm(pageCss: string, colorPrimary: string): boolean {
  const norm = pageCss.replace(/\s+/g, ' ').toLowerCase();
  const colour = colorPrimary.toLowerCase();
  if (!norm.includes(colour)) return false;
  const ruleRe = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = ruleRe.exec(norm)) !== null) {
    const selector = match[1];
    const body = match[2];
    if (body.includes(colour) && OWN_ELEMENT_SELECTORS.some((sel) => selector.includes(sel))) {
      return true;
    }
  }
  return false;
}

/** Largest multi-column (>1) `grid-template-columns` track count for the form's group container. */
function multiColumnTrackCount(pageCss: string): number {
  const norm = pageCss.replace(/\s+/g, ' ').toLowerCase();
  const containerSelectors = [
    '.application-form .form-group',
    '.application-form .form-field',
    '.application-form .form-grid',
    '.application-form main',
    '.application-form',
  ];
  let best = 0;
  const ruleRe = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = ruleRe.exec(norm)) !== null) {
    const selector = match[1];
    const body = match[2];
    if (!body.includes('grid-template-columns')) continue;
    if (!containerSelectors.some((sel) => selector.includes(sel))) continue;
    const repeat = /repeat\(\s*(\d+)/.exec(body);
    if (repeat && Number(repeat[1]) > 1) best = Math.max(best, Number(repeat[1]));
  }
  return best;
}

// ── Fixture / drift guards (both planes read the SAME attributes) ─────────────────────

describe('bugfix Task 20 — applied-appearance parity (preview half): shared fixture', () => {
  it('the two fixture copies are byte-identical (drift guard, Req 2.6 / spec-15 Req 7.1)', () => {
    const frontendBytes = readFileSync(FRONTEND_FIXTURE);
    const samBytes = readFileSync(SAM_FIXTURE);
    expect(frontendBytes.equals(samBytes)).toBe(true);
  });

  it('every case carries distinct observable values (colour ≠ default, columns>1, logo, title)', () => {
    expect(CASES.length).toBeGreaterThan(0);
    for (const c of CASES) {
      expect(c.input.color_primary.toLowerCase()).not.toBe(DEFAULT_PRIMARY.toLowerCase());
      expect(Number(c.input.columns)).toBeGreaterThan(1);
      expect(c.input.logo.trim().length).toBeGreaterThan(0);
      expect(c.input.header_title.trim().length).toBeGreaterThan(0);
    }
  });
});

// ── The applied-appearance assertions on the PREVIEW ──────────────────────────────────

describe('bugfix Task 20 — the preview applies the shared fixture attributes', () => {
  it.each(CASES.map((c) => [c.name, c] as const))(
    'preview applies the brand colour / columns / logo / heading for case %s (Req 2.6)',
    (_name, testCase) => {
      const lookAndFeel = testCase.input as unknown as LookAndFeelSettings;

      render(
        <ApplicationFormPreview
          fieldConfig={onFormConfig()}
          overlay={{}}
          lang="en"
          lookAndFeel={lookAndFeel}
        />,
      );

      const container = screen.getByTestId('application-form-preview-render');

      // (a) brand colour APPLIED to the form's own elements — asserted over the page CSS the
      // preview actually consumes (the Layer-2 mirror output), using the SAME applied-colour
      // predicate the SAM published-artifact test uses. Not a string-equality compare.
      const { pageCss } = renderPageStyles(lookAndFeel);
      expect(appliesBrandColourToForm(pageCss, testCase.input.color_primary)).toBe(true);

      // (b) the `columns` value drives the field-group grid track count — the APPLIED column
      // count the preview resolved (exposed on the container) matches the fixture, AND the
      // Layer-2 page CSS the preview consumes declares the same multi-column grid.
      expect(container.getAttribute('data-lookandfeel-columns')).toBe(testCase.input.columns);
      expect(multiColumnTrackCount(pageCss)).toBe(Number(testCase.input.columns));

      // (c) the tenant logo is rendered as an <img> with the fixture src.
      const logo = screen.getByTestId('application-form-preview-logo');
      expect(logo).toHaveAttribute('src', testCase.input.logo);

      // (d) the header title is rendered as a visible heading carrying the fixture text.
      const title = screen.getByTestId('application-form-preview-title');
      expect(title).toHaveTextContent(testCase.input.header_title);
    },
  );

  it('the preview resolves the SAME applied column count the published path declares (parity)', () => {
    // Cross-check: for each case the preview's resolved column count (the number it lays the
    // field groups out in) equals the multi-column track count the shared Layer-2 page CSS
    // declares — so the two paths cannot diverge on the applied column count. An out-of-range
    // value would clamp identically on both (authoritative rejection lives at the edge/service).
    for (const c of CASES) {
      const lookAndFeel = c.input as unknown as LookAndFeelSettings;
      const { unmount } = render(
        <ApplicationFormPreview
          fieldConfig={onFormConfig()}
          overlay={{}}
          lang="en"
          lookAndFeel={lookAndFeel}
        />,
      );
      const previewColumns = Number(
        screen.getByTestId('application-form-preview-render').getAttribute('data-lookandfeel-columns'),
      );
      const cssColumns = multiColumnTrackCount(renderPageStyles(lookAndFeel).pageCss);
      // Both derive from the SAME resolved value + SAME clamp, so they agree (and equal the
      // fixture's in-range value).
      expect(previewColumns).toBe(cssColumns);
      expect(previewColumns).toBe(Number(c.input.columns));
      unmount();
    }
  });

  it('a tenant on pure defaults (no fixture attrs) renders no logo/heading and the default columns', () => {
    // The parity holds at the "absent" end too: with no look-and-feel the preview renders neither
    // logo nor heading and falls back to the SAM-owned default column count — exactly as the
    // published path renders a defaults-only tenant (preservation of the no-attrs appearance).
    render(<ApplicationFormPreview fieldConfig={onFormConfig()} overlay={{}} lang="en" />);
    expect(screen.queryByTestId('application-form-preview-logo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-form-preview-title')).not.toBeInTheDocument();
    expect(
      screen.getByTestId('application-form-preview-render').getAttribute('data-lookandfeel-columns'),
    ).toBe(DEFAULTS.columns);
  });
});
