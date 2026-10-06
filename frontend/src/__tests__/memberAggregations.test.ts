/**
 * Unit + property tests for the Member Analytics numeric-aggregation helpers.
 *
 * Covers `toNumber` parsing (valid / absent / non-numeric), `mean` over
 * present-only values, and `countExcluded` of absent/invalid inputs.
 *
 * Spec: `.kiro/specs/Members/member-analytics` (design C2; R2.1, R2.3, R3.5).
 */
import fc from 'fast-check';
import {
  toNumber,
  mean,
  countExcluded,
} from '../components/members/analytics/memberAggregations';

describe('memberAggregations.toNumber', () => {
  describe('valid numeric input', () => {
    it('returns a finite number unchanged', () => {
      expect(toNumber(42)).toBe(42);
      expect(toNumber(0)).toBe(0);
      expect(toNumber(-7)).toBe(-7);
      expect(toNumber(3.5)).toBe(3.5);
    });

    it('parses a numeric string', () => {
      expect(toNumber('42')).toBe(42);
      expect(toNumber('3.5')).toBe(3.5);
      expect(toNumber('-7')).toBe(-7);
      expect(toNumber('0')).toBe(0);
    });

    it('tolerates surrounding whitespace on a numeric string', () => {
      expect(toNumber('  42  ')).toBe(42);
      expect(toNumber('\t12\n')).toBe(12);
    });
  });

  describe('absent input', () => {
    it('returns null for null / undefined', () => {
      expect(toNumber(null)).toBeNull();
      expect(toNumber(undefined)).toBeNull();
    });

    it('returns null for an empty or whitespace-only string', () => {
      expect(toNumber('')).toBeNull();
      expect(toNumber('   ')).toBeNull();
    });
  });

  describe('non-numeric input', () => {
    it('returns null for a non-numeric string', () => {
      expect(toNumber('abc')).toBeNull();
    });

    it('returns null for a string with trailing garbage', () => {
      // Number('12abc') is NaN — unlike parseFloat we reject partial parses.
      expect(toNumber('12abc')).toBeNull();
      expect(toNumber('42 jaar')).toBeNull();
    });

    it('returns null for non-finite numbers', () => {
      expect(toNumber(NaN)).toBeNull();
      expect(toNumber(Infinity)).toBeNull();
      expect(toNumber(-Infinity)).toBeNull();
    });

    it('returns null for non-string, non-number types', () => {
      expect(toNumber(true)).toBeNull();
      expect(toNumber(false)).toBeNull();
      expect(toNumber({})).toBeNull();
      expect(toNumber([])).toBeNull();
      expect(toNumber([1, 2])).toBeNull();
    });
  });
});

describe('memberAggregations.mean', () => {
  it('averages a list of numbers', () => {
    expect(mean([2, 4, 6])).toBe(4);
    expect(mean([10])).toBe(10);
  });

  it('averages numeric strings (parsed via toNumber)', () => {
    // Mirrors the stringified `age` / `years_member` calculated fields.
    expect(mean(['40', '50', '60'])).toBe(50);
  });

  it('computes the mean over present-only values, excluding absent/invalid', () => {
    // 40 and 60 are present → mean 50; null, '', 'abc' are excluded, NOT 0.
    expect(mean([40, null, '', 'abc', 60])).toBe(50);
  });

  it('returns null when no value is present or valid', () => {
    expect(mean([])).toBeNull();
    expect(mean([null, undefined, '', 'abc'])).toBeNull();
  });

  it('does not treat excluded rows as zero (regression on R2.3)', () => {
    // If invalid rows were counted as 0, the mean of [50, invalid] would be 25.
    expect(mean([50, 'nope'])).toBe(50);
  });
});

describe('memberAggregations.countExcluded', () => {
  it('counts absent and invalid inputs', () => {
    expect(countExcluded([40, null, '', 'abc', 60])).toBe(3);
  });

  it('returns 0 when every input is valid', () => {
    expect(countExcluded([1, '2', 3])).toBe(0);
  });

  it('counts every entry when none are valid', () => {
    expect(countExcluded([null, undefined, '', 'x'])).toBe(4);
  });

  it('returns 0 for an empty input', () => {
    expect(countExcluded([])).toBe(0);
  });
});

describe('memberAggregations — properties (fast-check)', () => {
  /**
   * present-count + excluded-count === total: every row is classified as either
   * aggregatable or excluded, never both, never neither.
   *
   * Validates: Requirements 2.3
   */
  it('present + excluded always equals the total row count', () => {
    const anyValue = fc.oneof(
      fc.integer(),
      fc.float({ noNaN: false }),
      fc.string(),
      fc.constant(null),
      fc.constant(undefined),
      fc.boolean(),
    );
    fc.assert(
      fc.property(fc.array(anyValue), (values) => {
        const excluded = countExcluded(values);
        const present = values.filter((v) => toNumber(v) !== null).length;
        expect(present + excluded).toBe(values.length);
      }),
      { numRuns: 200 },
    );
  });

  /**
   * The mean of a non-empty set of finite numbers lies within [min, max] and a
   * constant list averages to that constant.
   *
   * Validates: Requirements 2.3
   */
  it('mean of finite numbers stays within [min, max]', () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: -1_000_000, max: 1_000_000 }), { minLength: 1 }),
        (nums) => {
          const m = mean(nums);
          expect(m).not.toBeNull();
          expect(m as number).toBeGreaterThanOrEqual(Math.min(...nums));
          expect(m as number).toBeLessThanOrEqual(Math.max(...nums));
        },
      ),
      { numRuns: 200 },
    );
  });
});
