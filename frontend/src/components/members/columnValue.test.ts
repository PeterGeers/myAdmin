/**
 * columnValue.coerceByType — session-columns task 2.1 (design C4; R2.3).
 *
 * The surfaced-column flatten feeds the overview SORT, which compares the raw
 * flat value. Verifies the type-aware coercion that makes R2.3 (number → numeric
 * order, date → chronological order, else string-safe) hold, with graceful
 * fallbacks for NaN / empty / bad-date so a malformed cell never becomes `NaN`
 * or `"Invalid Date"` and never corrupts the ordering.
 *
 * **Validates: Requirements 2.3**
 */

import { describe, it, expect } from 'vitest';
import type { FieldConfigField } from '../../types/members';
import { coerceByType, FLAT_ALIASES, isFlatAlias, shouldFlatten } from './columnValue';

const field = (over: Partial<FieldConfigField> = {}): FieldConfigField => ({
  key: 'k',
  ...over,
});

describe('columnValue.coerceByType — number', () => {
  const numField = field({ type: 'number' });

  it('coerces a numeric string to a real number (numeric sort, not lexical)', () => {
    expect(coerceByType(numField, '12')).toBe(12);
    expect(coerceByType(numField, '9')).toBe(9);
    // Proves numeric ordering: 9 < 12 as numbers (lexically "12" < "9").
    const a = coerceByType(numField, '9') as number;
    const b = coerceByType(numField, '12') as number;
    expect(a < b).toBe(true);
  });

  it('passes a real number through unchanged', () => {
    expect(coerceByType(numField, 42)).toBe(42);
    expect(coerceByType(numField, 0)).toBe(0);
    expect(coerceByType(numField, -3.5)).toBe(-3.5);
  });

  it('falls back to the original value when the number is NaN', () => {
    expect(coerceByType(numField, 'not-a-number')).toBe('not-a-number');
    expect(coerceByType(numField, 'abc123')).toBe('abc123');
  });

  it('falls back to the original value for an empty/blank string (not 0)', () => {
    expect(coerceByType(numField, '')).toBe('');
    expect(coerceByType(numField, '   ')).toBe('   ');
  });

  it('falls back to the original value for a non-finite number', () => {
    expect(coerceByType(numField, Infinity)).toBe(Infinity);
    expect(coerceByType(numField, NaN)).toBeNaN();
  });
});

describe('columnValue.coerceByType — date', () => {
  const dateField = field({ type: 'date' });

  it('coerces an ISO date string to a sortable ISO form', () => {
    const out = coerceByType(dateField, '2000-01-15') as string;
    expect(typeof out).toBe('string');
    expect(out.startsWith('2000-01-15')).toBe(true);
  });

  it('produces a chronologically-sortable form (not a lexical one)', () => {
    const earlier = coerceByType(dateField, '2019-12-31') as string;
    const later = coerceByType(dateField, '2020-01-01') as string;
    expect(earlier < later).toBe(true);
  });

  it('accepts a Date instance', () => {
    const d = new Date('2010-06-01T00:00:00.000Z');
    expect(coerceByType(dateField, d)).toBe(d.toISOString());
  });

  it('falls back to the original value for an unparseable (bad) date', () => {
    expect(coerceByType(dateField, 'not-a-date')).toBe('not-a-date');
    expect(coerceByType(dateField, 'tomorrow')).toBe('tomorrow');
  });

  it('falls back to the original value for an empty/blank date string', () => {
    expect(coerceByType(dateField, '')).toBe('');
    expect(coerceByType(dateField, '   ')).toBe('   ');
  });
});

describe('columnValue.coerceByType — other / default', () => {
  it('returns a String-safe value for string-typed fields', () => {
    expect(coerceByType(field({ type: 'string' }), 'hello')).toBe('hello');
    expect(coerceByType(field({ type: 'string' }), 7)).toBe('7');
  });

  it('returns a String-safe value when the type is omitted', () => {
    expect(coerceByType(field(), 'plain')).toBe('plain');
    expect(coerceByType(field(), true)).toBe('true');
  });

  it('returns a String-safe value for enum / reference types', () => {
    expect(coerceByType(field({ type: 'enum' }), 'active')).toBe('active');
    expect(coerceByType(field({ type: 'reference' }), 123)).toBe('123');
  });
});

describe('columnValue.coerceByType — absent values', () => {
  it('passes null and undefined through untouched for every type', () => {
    for (const type of ['number', 'date', 'string', undefined]) {
      expect(coerceByType(field({ type }), null)).toBeNull();
      expect(coerceByType(field({ type }), undefined)).toBeUndefined();
    }
  });
});

/**
 * FLAT_ALIASES + the exclusion helpers — session-columns task 2.2 (design C4;
 * R3.4). The on-the-fly flatten must never clobber an existing flat alias: only
 * non-alias keys are promoted.
 *
 * **Validates: Requirements 3.4**
 */
describe('columnValue.FLAT_ALIASES (R3.4 no flat-alias collision)', () => {
  // The exact aliases flattenMember promotes onto every row. Kept in lockstep
  // with that function; a drift here means the on-the-fly flatten could clobber
  // an alias (R3.4).
  const EXPECTED_ALIASES = [
    'member_number',
    'name',
    'email',
    'status',
    'membership_type',
    'region',
    'membership_id',
  ];

  it('contains exactly the keys flattenMember already promotes', () => {
    expect([...FLAT_ALIASES].sort()).toEqual([...EXPECTED_ALIASES].sort());
    expect(FLAT_ALIASES.size).toBe(EXPECTED_ALIASES.length);
  });

  it('isFlatAlias recognizes every promoted key', () => {
    for (const key of EXPECTED_ALIASES) {
      expect(isFlatAlias(key)).toBe(true);
    }
  });

  it('isFlatAlias rejects a non-alias / nested candidate key', () => {
    expect(isFlatAlias('years_member')).toBe(false);
    expect(isFlatAlias('birth_date')).toBe(false);
    expect(isFlatAlias('signature_date')).toBe(false);
    expect(isFlatAlias('')).toBe(false);
  });
});

describe('columnValue.shouldFlatten (C4 exclusion of flat aliases)', () => {
  it('excludes every flat alias from flattening', () => {
    for (const key of FLAT_ALIASES) {
      expect(shouldFlatten(key)).toBe(false);
    }
  });

  it('includes a non-alias nested/calculated key for flattening', () => {
    expect(shouldFlatten('years_member')).toBe(true);
    expect(shouldFlatten('birth_date')).toBe(true);
    expect(shouldFlatten('age')).toBe(true);
  });

  it('is the exact complement of isFlatAlias', () => {
    for (const key of ['member_number', 'years_member', 'region', 'birth_date', '']) {
      expect(shouldFlatten(key)).toBe(!isFlatAlias(key));
    }
  });

  it('filters a chosen column list to only non-alias keys (the C4 use site)', () => {
    const chosen = ['member_number', 'years_member', 'region', 'signature_date'];
    expect(chosen.filter(shouldFlatten)).toEqual(['years_member', 'signature_date']);
  });
});
