/**
 * labelResolver.test — the ONE shared localized-label resolver
 * (code-quality-fixes-2026-10-28 task 1).
 *
 * The 8 former `resolveLabel` copies collapsed into {@link resolveLabel} came in TWO
 * test-pinned behavioral variants that must BOTH survive consolidation:
 *
 *   - `'en-first'` (default): active → `en` → `nl` → key, blank-as-absent, plain empty
 *     string → key. This is the serializer-matching i18n contract (`fieldForm.ts`,
 *     `applicationForm.model.ts`), cross-pinned by `fieldForm.test.ts`.
 *   - `'nl-first'`: active → `nl` → `en` → key, plain string passed through verbatim.
 *     This is the checklist/analytics convention (`FieldChecklist`, the analytics
 *     helpers/page), cross-pinned by `FieldChecklist.test.tsx`.
 *
 * This suite exercises the shared util directly so the ordering + empty-string nuance is
 * locked at the single source, not only through the per-site re-exports.
 */

import { describe, it, expect } from 'vitest';
import { resolveLabel } from './labelResolver';

const KEY = 'membersConfig.field.first_name';

describe("resolveLabel 'en-first' (default) — active → en → nl → key, blank-as-absent", () => {
  it('uses the active locale when present', () => {
    expect(resolveLabel({ de: 'Vorname', en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe(
      'Vorname',
    );
  });

  it('prefers en over nl when the active locale is missing', () => {
    expect(resolveLabel({ en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe('First name');
    expect(resolveLabel({ en: 'Address', nl: 'Adres' }, 'fr', KEY)).toBe('Address');
  });

  it('falls back to nl when active and en are both absent', () => {
    expect(resolveLabel({ nl: 'Voornaam' }, 'de', KEY)).toBe('Voornaam');
  });

  it('falls back to the key — never blank — when no locale resolves', () => {
    expect(resolveLabel({}, 'de', KEY)).toBe(KEY);
    expect(resolveLabel(undefined, 'de', KEY)).toBe(KEY);
  });

  it('treats a blank value at any tier as absent (never render "")', () => {
    expect(resolveLabel({ de: '', en: 'First name', nl: 'Voornaam' }, 'de', KEY)).toBe(
      'First name',
    );
    expect(resolveLabel({ de: '', en: '', nl: 'Voornaam' }, 'de', KEY)).toBe('Voornaam');
    expect(resolveLabel({ de: '', en: '', nl: '' }, 'de', KEY)).toBe(KEY);
  });

  it('passes a plain string through but maps an empty string to the key', () => {
    expect(resolveLabel('Literal', 'de', KEY)).toBe('Literal');
    expect(resolveLabel('', 'de', KEY)).toBe(KEY);
  });

  it("the default order IS 'en-first' (omitted arg matches explicit)", () => {
    const label = { en: 'First name', nl: 'Voornaam' };
    expect(resolveLabel(label, 'de', KEY)).toBe(resolveLabel(label, 'de', KEY, 'en-first'));
  });
});

describe("resolveLabel 'nl-first' — active → nl → en → key, plain string passed through", () => {
  it('uses the active locale when present', () => {
    expect(resolveLabel({ nl: 'Naam', en: 'Name' }, 'nl', 'k', 'nl-first')).toBe('Naam');
    expect(resolveLabel({ nl: 'Naam', en: 'Name' }, 'en', 'k', 'nl-first')).toBe('Name');
  });

  it('prefers nl over en when the active locale is missing', () => {
    expect(resolveLabel({ nl: 'Naam', en: 'Name' }, 'de', 'k', 'nl-first')).toBe('Naam');
  });

  it('falls back active → nl → en → key', () => {
    expect(resolveLabel({ en: 'Name' }, 'nl', 'k', 'nl-first')).toBe('Name');
    expect(resolveLabel({ nl: 'Naam' }, 'en', 'k', 'nl-first')).toBe('Naam');
    expect(resolveLabel(undefined, 'en', 'k', 'nl-first')).toBe('k');
    expect(resolveLabel({}, 'en', 'k', 'nl-first')).toBe('k');
  });

  it('passes a non-empty plain string through verbatim', () => {
    expect(resolveLabel('Plain', 'en', 'k', 'nl-first')).toBe('Plain');
    // An empty-string label is falsy → the `!label` guard returns the key in BOTH
    // orders (the original FieldChecklist copy did the same: `if (!label) return fallback`).
    expect(resolveLabel('', 'en', 'k', 'nl-first')).toBe('k');
  });
});

describe('resolveLabel — add-a-language is pure data (no per-language branch)', () => {
  it('resolves a newly-added locale with no code change, in both orders', () => {
    expect(resolveLabel({ nl: 'Adres', en: 'Address', fr: 'Adresse' }, 'fr', KEY)).toBe('Adresse');
    expect(resolveLabel({ nl: 'Adres', en: 'Address', xx: 'Xx' }, 'xx', KEY, 'nl-first')).toBe(
      'Xx',
    );
  });
});
