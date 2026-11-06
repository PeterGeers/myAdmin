/**
 * Tests for the browser-side TS Layer-2 CSS generator `pageStyles.ts` (spec 15 — SAM Page
 * Look-and-Feel, task 13.1; DD-3 option 1, design §C5).
 *
 * `renderPageStyles` is the React (preview-path) MIRROR of the SAM-owned Python Layer-2
 * generator `sam/shared/page_styles/__init__.py`. These tests pin the TS behaviour to the
 * Python contract so the preview matches what publish bakes (Req 7): the same seven supported
 * attributes, the same SAM-owned defaults, the same enum lookup maps, and the same
 * determinism / rejection / defaulting rules. Task 13.2 (a later wave) adds the shared
 * cross-language parity FIXTURE; this suite verifies the TS output is correct and self-consistent.
 *
 * Both unit tests (specific examples, the exact default/enum values) and property-based tests
 * (determinism, defaulting, difference, rejection — the universal Layer-2 properties over the
 * structured settings space) are included; they complement each other.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import {
  renderPageStyles,
  SUPPORTED_ATTRIBUTES,
  DEFAULTS,
  UnsupportedAttributeError,
  type LookAndFeelSettings,
  type SupportedAttribute,
} from './pageStyles';

// The permitted enum values per attribute — mirror the Python lookup-map keys / theme choices.
const SPACING_VALUES = ['compact', 'normal', 'relaxed'] as const;
const RADIUS_VALUES = ['sharp', 'rounded', 'pill'] as const;
const SHADOW_VALUES = ['none', 'subtle', 'medium', 'dramatic'] as const;

describe('renderPageStyles — supported attributes + defaults (Req 3.2, 3.3)', () => {
  it('supports exactly the seven attributes the Python generator supports (Req 3.2)', () => {
    expect([...SUPPORTED_ATTRIBUTES].sort()).toEqual(
      [
        'base_spacing',
        'border_radius_global',
        'color_accent',
        'color_primary',
        'font_body',
        'font_heading',
        'shadow_style',
      ].sort(),
    );
  });

  it('pins the SAM-owned defaults exactly (mirror of the Python _DEFAULTS map)', () => {
    expect(DEFAULTS).toEqual({
      color_primary: '#2D5F8A',
      color_accent: '#F4A261',
      font_heading: 'system',
      font_body: 'system',
      base_spacing: 'normal',
      border_radius_global: 'rounded',
      shadow_style: 'subtle',
    });
  });

  it('with NO settings, emits the default :root block (system fonts, normal/rounded/subtle)', () => {
    const { cssVariables, cssVariableMap, fontLinks } = renderPageStyles({});

    // System fonts → the system font stack, no web-font <link> tags.
    expect(cssVariableMap['--font-heading']).toBe(
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    );
    expect(cssVariableMap['--font-body']).toBe(
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    );
    expect(fontLinks).toBe('');

    // normal spacing / rounded radius / subtle shadow — the enum-map default rows.
    expect(cssVariableMap['--spacing-section']).toBe('2rem');
    expect(cssVariableMap['--spacing-element']).toBe('1rem');
    expect(cssVariableMap['--radius-sm']).toBe('4px');
    expect(cssVariableMap['--radius-md']).toBe('8px');
    expect(cssVariableMap['--radius-lg']).toBe('16px');
    expect(cssVariableMap['--shadow-card']).toBe('0 2px 8px rgba(0,0,0,0.08)');
    expect(cssVariableMap['--shadow-hover']).toBe('0 4px 16px rgba(0,0,0,0.12)');

    // The :root string is built from the same map and carries the block delimiters.
    expect(cssVariables.startsWith(':root {')).toBe(true);
    expect(cssVariables.endsWith('}')).toBe(true);
    expect(cssVariables).toContain('--shadow-card: 0 2px 8px rgba(0,0,0,0.08);');
  });

  it('bakes the two brand-colour defaults into the page CSS when none supplied (Req 5.4)', () => {
    const { pageCss } = renderPageStyles({});
    // Primary tints headings/CTA; accent tints buttons.
    expect(pageCss).toContain('color: #2D5F8A;');
    expect(pageCss).toContain('background: #F4A261;');
  });
});

describe('renderPageStyles — enum attribute lookups (mirror the Python maps)', () => {
  it('maps base_spacing to the correct section/element pair', () => {
    expect(renderPageStyles({ base_spacing: 'compact' }).cssVariableMap['--spacing-section']).toBe(
      '1.5rem',
    );
    expect(renderPageStyles({ base_spacing: 'relaxed' }).cssVariableMap['--spacing-element']).toBe(
      '1.5rem',
    );
  });

  it('maps border_radius_global to the correct sm/md/lg triple', () => {
    const sharp = renderPageStyles({ border_radius_global: 'sharp' }).cssVariableMap;
    expect([sharp['--radius-sm'], sharp['--radius-md'], sharp['--radius-lg']]).toEqual([
      '0',
      '0',
      '0',
    ]);
    const pill = renderPageStyles({ border_radius_global: 'pill' }).cssVariableMap;
    expect([pill['--radius-sm'], pill['--radius-md'], pill['--radius-lg']]).toEqual([
      '12px',
      '24px',
      '9999px',
    ]);
  });

  it('maps shadow_style to the correct card/hover pair', () => {
    const none = renderPageStyles({ shadow_style: 'none' }).cssVariableMap;
    expect(none['--shadow-card']).toBe('none');
    expect(none['--shadow-hover']).toBe('none');
    const dramatic = renderPageStyles({ shadow_style: 'dramatic' }).cssVariableMap;
    expect(dramatic['--shadow-card']).toBe('0 8px 24px rgba(0,0,0,0.2)');
    expect(dramatic['--shadow-hover']).toBe('0 16px 48px rgba(0,0,0,0.28)');
  });

  it('an unknown enum value falls back to the map default (not a failure)', () => {
    // Mirrors the Python `_MAP.get(value, _MAP["default"])` — out-of-map value → default row.
    const vars = renderPageStyles({
      base_spacing: 'enormous',
      border_radius_global: 'squircle',
      shadow_style: 'neon',
    }).cssVariableMap;
    expect(vars['--spacing-section']).toBe('2rem'); // normal
    expect(vars['--radius-md']).toBe('8px'); // rounded
    expect(vars['--shadow-card']).toBe('0 2px 8px rgba(0,0,0,0.08)'); // subtle
  });
});

describe('renderPageStyles — fonts (Req 3.2)', () => {
  it('a web font quotes the family and emits Google-Font <link> tags', () => {
    const { cssVariableMap, fontLinks } = renderPageStyles({
      font_heading: 'Inter',
      font_body: 'Inter',
    });
    expect(cssVariableMap['--font-heading']).toBe('"Inter", sans-serif');
    expect(cssVariableMap['--font-body']).toBe('"Inter", sans-serif');
    expect(fontLinks).toContain('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700');
    expect(fontLinks).toContain('rel="preconnect"');
  });

  it('a space in a font family becomes a + in the Google-Font URL and families are sorted', () => {
    const { fontLinks } = renderPageStyles({
      font_heading: 'Open Sans',
      font_body: 'Roboto Slab',
    });
    // Sorted: "Open Sans" < "Roboto Slab"; spaces → +.
    expect(fontLinks).toContain(
      'family=Open+Sans:wght@400;600;700&family=Roboto+Slab:wght@400;600;700',
    );
  });

  it('system fonts load no stylesheet (empty font links)', () => {
    expect(renderPageStyles({ font_heading: 'system', font_body: 'system' }).fontLinks).toBe('');
  });
});

describe('renderPageStyles — sanitisation (parity with the Python _UNSAFE_PATTERN)', () => {
  it('strips url(…) / expression(…) / javascript: from a brand colour before it reaches CSS', () => {
    const { pageCss } = renderPageStyles({
      color_primary: 'url(evil.css)#2D5F8A',
      color_accent: 'javascript:alert(1)#F4A261',
    });
    expect(pageCss).not.toContain('url(');
    expect(pageCss).not.toContain('javascript:');
    expect(pageCss).not.toContain('expression(');
  });

  it('strips dangerous patterns from a font family too', () => {
    const { cssVariableMap } = renderPageStyles({ font_heading: 'expression(x)Evil' });
    expect(cssVariableMap['--font-heading']).not.toContain('expression(');
  });
});

describe('renderPageStyles — unsupported attribute rejection (Req 3.4)', () => {
  it('throws UnsupportedAttributeError naming the offending key and produces no styling', () => {
    expect(() => renderPageStyles({ color_primary: '#000', bogus_attr: 'x' })).toThrow(
      UnsupportedAttributeError,
    );
    try {
      renderPageStyles({ bogus_attr: 'x' } as LookAndFeelSettings);
      throw new Error('expected rejection');
    } catch (e) {
      expect(e).toBeInstanceOf(UnsupportedAttributeError);
      expect((e as UnsupportedAttributeError).attribute).toBe('bogus_attr');
    }
  });

  it('reports the FIRST unsupported key in sorted order (deterministic, mirrors Python sorted())', () => {
    try {
      renderPageStyles({ zzz_bad: '1', aaa_bad: '2' } as LookAndFeelSettings);
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as UnsupportedAttributeError).attribute).toBe('aaa_bad');
    }
  });
});

// ─── Property-based tests (fast-check) — the universal Layer-2 properties ──────────────────

/** An arbitrary over VALID settings mappings (subsets of the seven supported attributes). */
const settingsArb: fc.Arbitrary<LookAndFeelSettings> = fc.record(
  {
    color_primary: fc.constantFrom('#2D5F8A', '#112233', '#abcdef'),
    color_accent: fc.constantFrom('#F4A261', '#001122', '#ffeedd'),
    font_heading: fc.constantFrom('system', 'Inter', 'Open Sans', 'Lora'),
    font_body: fc.constantFrom('system', 'Inter', 'Roboto', 'Merriweather'),
    base_spacing: fc.constantFrom(...SPACING_VALUES),
    border_radius_global: fc.constantFrom(...RADIUS_VALUES),
    shadow_style: fc.constantFrom(...SHADOW_VALUES),
  },
  { requiredKeys: [] }, // any subset may be omitted → defaulting
);

describe('Feature: sam-page-look-and-feel, Property 1: Layer-2 output is deterministic in the settings', () => {
  // Validates: Requirements 1.2, 1.5
  it('invoking render twice with the same values produces identical output', () => {
    fc.assert(
      fc.property(settingsArb, (settings) => {
        const a = renderPageStyles(settings);
        const b = renderPageStyles(settings);
        expect(b).toEqual(a);
      }),
      { numRuns: 100 },
    );
  });
});

describe('Feature: sam-page-look-and-feel, Property 2: output depends only on the supplied values (page-type-agnostic)', () => {
  // Validates: Requirements 1.5, 4.3, 6.1, 6.2, 6.3
  it('two independent calls with identical values yield identical styling (Req 4.3)', () => {
    fc.assert(
      fc.property(settingsArb, (settings) => {
        // A fresh copy of the same values (different object identity) must produce identical output.
        const copy = { ...settings };
        expect(renderPageStyles(copy)).toEqual(renderPageStyles(settings));
      }),
      { numRuns: 100 },
    );
  });
});

describe('Feature: sam-page-look-and-feel, Property 3: different values produce correspondingly different styling', () => {
  // Validates: Requirements 4.2, 5.3
  it('changing one supported attribute to a different valid value changes the styling', () => {
    // Pairs of (attribute, two distinct valid values) that each MUST change observable output.
    const changers: Array<{ attr: SupportedAttribute; a: string; b: string }> = [
      { attr: 'color_primary', a: '#2D5F8A', b: '#111111' },
      { attr: 'color_accent', a: '#F4A261', b: '#222222' },
      { attr: 'font_heading', a: 'system', b: 'Inter' },
      { attr: 'font_body', a: 'system', b: 'Lora' },
      { attr: 'base_spacing', a: 'compact', b: 'relaxed' },
      { attr: 'border_radius_global', a: 'sharp', b: 'pill' },
      { attr: 'shadow_style', a: 'none', b: 'dramatic' },
    ];
    fc.assert(
      fc.property(fc.constantFrom(...changers), (c) => {
        const styleA = renderPageStyles({ [c.attr]: c.a });
        const styleB = renderPageStyles({ [c.attr]: c.b });
        // At least one of the three CSS pieces must differ for the changed attribute.
        const differs =
          styleA.cssVariables !== styleB.cssVariables ||
          styleA.pageCss !== styleB.pageCss ||
          styleA.fontLinks !== styleB.fontLinks;
        expect(differs).toBe(true);
      }),
      { numRuns: 100 },
    );
  });
});

describe('Feature: sam-page-look-and-feel, Property 4: absent attributes fall back to defaults without failing', () => {
  // Validates: Requirements 1.3, 3.3, 4.4, 5.4
  it('any subset of omitted attributes still renders, and omitting an attribute uses its default', () => {
    fc.assert(
      fc.property(
        // A random subset of attributes to OMIT.
        fc.subarray([...SUPPORTED_ATTRIBUTES]),
        (omit) => {
          const full: LookAndFeelSettings = {
            color_primary: '#2D5F8A',
            color_accent: '#F4A261',
            font_heading: 'Inter',
            font_body: 'Inter',
            base_spacing: 'compact',
            border_radius_global: 'sharp',
            shadow_style: 'medium',
          };
          const partial: LookAndFeelSettings = { ...full };
          for (const k of omit) delete partial[k];

          // Never throws for a valid (possibly incomplete) mapping.
          const result = renderPageStyles(partial);
          expect(result.cssVariables.startsWith(':root {')).toBe(true);

          // An omitted attribute must render identically to supplying its explicit default.
          const withDefaults: LookAndFeelSettings = { ...partial };
          for (const k of omit) withDefaults[k] = DEFAULTS[k];
          expect(renderPageStyles(partial)).toEqual(renderPageStyles(withDefaults));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('a null/undefined attribute value falls back to the default (clear-to-default)', () => {
    const nulled = renderPageStyles({ base_spacing: null, shadow_style: undefined });
    const defaulted = renderPageStyles({});
    expect(nulled).toEqual(defaulted);
  });
});

describe('Feature: sam-page-look-and-feel, Property 5: unsupported attribute is rejected and produces no styling', () => {
  // Validates: Requirements 3.4
  it('any mapping carrying a key outside the seven supported attributes throws, producing no output', () => {
    const unsupportedKey = fc
      .string({ minLength: 1, maxLength: 12 })
      .filter((k) => !(SUPPORTED_ATTRIBUTES as readonly string[]).includes(k) && k.trim() !== '');
    fc.assert(
      fc.property(settingsArb, unsupportedKey, fc.string(), (valid, badKey, badValue) => {
        const withBad: LookAndFeelSettings = { ...valid, [badKey]: badValue };
        expect(() => renderPageStyles(withBad)).toThrow(UnsupportedAttributeError);
      }),
      { numRuns: 100 },
    );
  });
});
