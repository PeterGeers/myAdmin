/**
 * Tests for the membership-type coherence helpers (spec 11, task 3.3; R4.1–R4.3, design §3/§9).
 *
 * The change-with-tests pairing for the pure R4 coherence logic the attributes panel special-cases
 * for the membership-type field:
 *  - identify the membership-type field by its canonical key/group (`membership.membership_type`);
 *  - the subset vocabulary is the LIVE catalog (`type_code`/legacy `key`), incl. retired entries;
 *  - an empty authored subset is flagged (R4.2) and an out-of-catalog value is flagged (R4.3),
 *    while a null/absent subset (the full catalog) is coherent.
 */
import { describe, it, expect } from 'vitest';
import type { FieldConfigField, MembershipType } from '../../../../types/members';
import {
  catalogChoices,
  catalogCodeOf,
  catalogCodeSet,
  isMembershipTypeField,
  validateMembershipSubset,
} from '../applicationMembershipType';

const CATALOG: MembershipType[] = [
  { type_code: 'regular', label: { en: 'Regular', nl: 'Gewoon' }, active: true, order: 1 },
  { type_code: 'honorary', label: { en: 'Honorary', nl: 'Erelid' }, active: true, order: 2 },
  { key: 'legacy', label: 'Legacy', active: false, order: 3 }, // legacy `key` alias, no type_code
];

describe('isMembershipTypeField (R4)', () => {
  it('matches the canonical membership-storage-group membership_type field', () => {
    const field = { key: 'membership_type', group: 'membership' } as FieldConfigField;
    expect(isMembershipTypeField(field)).toBe(true);
  });

  it('matches the bare canonical key when no storage group is served', () => {
    expect(isMembershipTypeField({ key: 'membership_type' } as FieldConfigField)).toBe(true);
  });

  it('does NOT match a different key, nor membership_type in another storage group', () => {
    expect(isMembershipTypeField({ key: 'status', group: 'membership' } as FieldConfigField)).toBe(false);
    expect(isMembershipTypeField({ key: 'membership_type', group: 'personal' } as FieldConfigField)).toBe(false);
    expect(isMembershipTypeField(null)).toBe(false);
  });
});

describe('catalog code helpers (R4.1/R4.3)', () => {
  it('prefers type_code, falls back to the legacy key alias', () => {
    expect(catalogCodeOf({ type_code: 'regular' })).toBe('regular');
    expect(catalogCodeOf({ key: 'legacy' })).toBe('legacy');
    expect(catalogCodeOf({})).toBe('');
  });

  it('catalogChoices offers every catalog entry (incl. retired) with resolved labels', () => {
    const choices = catalogChoices(CATALOG, 'en');
    expect(choices.map((c) => c.value)).toEqual(['regular', 'honorary', 'legacy']);
    expect(choices[0].label.en).toBe('Regular');
  });

  it('catalogChoices resolves the active-locale label (nl)', () => {
    expect(catalogChoices(CATALOG, 'nl')[0].label.nl).toBe('Gewoon');
  });

  it('catalogCodeSet is the set of live catalog codes', () => {
    expect(catalogCodeSet(CATALOG)).toEqual(new Set(['regular', 'honorary', 'legacy']));
  });

  it('a null/empty catalog yields no choices', () => {
    expect(catalogChoices(null, 'en')).toEqual([]);
    expect(catalogChoices([], 'en')).toEqual([]);
  });
});

describe('validateMembershipSubset (R4.2/R4.3)', () => {
  it('a null/absent subset (full catalog) is coherent — never flagged', () => {
    expect(validateMembershipSubset(null, CATALOG)).toEqual({ ok: true, empty: false, unknownValues: [] });
    expect(validateMembershipSubset(undefined, CATALOG)).toEqual({ ok: true, empty: false, unknownValues: [] });
  });

  it('an empty authored subset is flagged empty (R4.2)', () => {
    const res = validateMembershipSubset([], CATALOG);
    expect(res.empty).toBe(true);
    expect(res.ok).toBe(false);
  });

  it('a proper subset of live catalog codes is coherent', () => {
    expect(validateMembershipSubset(['regular', 'honorary'], CATALOG)).toEqual({
      ok: true,
      empty: false,
      unknownValues: [],
    });
  });

  it('out-of-catalog values are flagged (R4.3)', () => {
    const res = validateMembershipSubset(['regular', 'ghost'], CATALOG);
    expect(res.unknownValues).toEqual(['ghost']);
    expect(res.ok).toBe(false);
  });

  it('every value unknown when the catalog is empty (R4.3)', () => {
    const res = validateMembershipSubset(['regular'], []);
    expect(res.unknownValues).toEqual(['regular']);
    expect(res.ok).toBe(false);
  });
});
