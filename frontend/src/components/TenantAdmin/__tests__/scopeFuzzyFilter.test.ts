/**
 * scopeFuzzyFilter — Unit Tests (s5d task 6.3)
 *
 * The fuzzy typeahead is an AUTHORING CONVENIENCE (R5.4): it narrows WHICH
 * canonical values are shown, folding both query and candidate the same way the
 * backend `scope_canon` does (NFKD → strip diacritics → lowercase → fold
 * space/`-`/`/` → trim), then matching by substring. The RETURNED value is always
 * the ORIGINAL canonical spelling — fuzzy never changes what is stored (R5.3).
 *
 * Covers:
 *  - diacritic-insensitivity (accented query ↔ unaccented value and vice-versa),
 *  - spacing/separator tolerance (the design example "noord holl" → "Noord-Holland"),
 *  - case-insensitivity,
 *  - empty/whitespace query returns ALL values,
 *  - no match returns [],
 *  - returned values keep the ORIGINAL canonical spelling (never the folded form).
 */

import { fuzzyFilterValues, scopeCanonFold } from '../scopeFuzzyFilter';

describe('scopeCanonFold (match-form fold mirroring backend scope_canon)', () => {
  test('strips diacritics', () => {
    expect(scopeCanonFold('Fryslân')).toBe('fryslan');
    expect(scopeCanonFold('Frýslan')).toBe('fryslan');
    expect(scopeCanonFold('Noord-Hôlland')).toBe('noord holland');
  });

  test('folds space / - / / runs to one space and lowercases', () => {
    expect(scopeCanonFold('Noord-Holland')).toBe('noord holland');
    expect(scopeCanonFold('Noord Holland')).toBe('noord holland');
    expect(scopeCanonFold('Noord / Holland')).toBe('noord holland');
    expect(scopeCanonFold('  NOORD   HOLLAND  ')).toBe('noord holland');
  });
});

describe('fuzzyFilterValues (diacritic/spacing-tolerant typeahead)', () => {
  const provinces = ['Fryslân', 'Friesland', 'Noord-Holland', 'Zuid-Holland', 'Overijssel'];

  test('empty query returns all values (unchanged)', () => {
    expect(fuzzyFilterValues(provinces, '')).toEqual(provinces);
  });

  test('whitespace-only query returns all values', () => {
    expect(fuzzyFilterValues(provinces, '   ')).toEqual(provinces);
  });

  test('design example: "noord holl" matches "Noord-Holland"', () => {
    expect(fuzzyFilterValues(provinces, 'noord holl')).toEqual(['Noord-Holland']);
  });

  test('spacing/separator tolerant: hyphen, space, and slash queries all match', () => {
    expect(fuzzyFilterValues(provinces, 'noord-holland')).toEqual(['Noord-Holland']);
    expect(fuzzyFilterValues(provinces, 'noord holland')).toEqual(['Noord-Holland']);
    expect(fuzzyFilterValues(provinces, 'zuid / holland')).toEqual(['Zuid-Holland']);
  });

  test('case-insensitive', () => {
    expect(fuzzyFilterValues(provinces, 'FRIES')).toEqual(['Friesland']);
    expect(fuzzyFilterValues(['Noord', 'Oost', 'Zuid'], 'oo')).toEqual(['Noord', 'Oost']);
  });

  test('diacritic-insensitive: unaccented query matches accented value', () => {
    // "fryslan" (no accent) → "Fryslân"
    expect(fuzzyFilterValues(provinces, 'fryslan')).toEqual(['Fryslân']);
    // "friesland" → "Friesland"
    expect(fuzzyFilterValues(provinces, 'friesland')).toEqual(['Friesland']);
  });

  test('diacritic-insensitive: accented query matches its value (and unaccented one)', () => {
    // Accented query variants all fold to "fryslan" and match "Fryslân".
    expect(fuzzyFilterValues(['Fryslân'], 'Frýslan')).toEqual(['Fryslân']);
    expect(fuzzyFilterValues(['Fryslân'], 'Fryslân')).toEqual(['Fryslân']);
    expect(fuzzyFilterValues(['Fryslân'], 'Fryslan')).toEqual(['Fryslân']);
  });

  test('no match returns []', () => {
    expect(fuzzyFilterValues(provinces, 'zeeland')).toEqual([]);
  });

  test('returns the ORIGINAL canonical spelling, never the folded form (R5.3)', () => {
    const [match] = fuzzyFilterValues(provinces, 'noord holl');
    // The stored/returned value keeps its accents, separators, and case.
    expect(match).toBe('Noord-Holland');
    expect(fuzzyFilterValues(provinces, 'fryslan')[0]).toBe('Fryslân');
  });

  test('preserves original order and returns all matching values', () => {
    // Both Holland provinces fold to contain "holland".
    expect(fuzzyFilterValues(provinces, 'holland')).toEqual(['Noord-Holland', 'Zuid-Holland']);
  });
});
