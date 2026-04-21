/**
 * Property-based tests for date sorting fix in compareValues
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Property 1 (Bug Condition Exploration):
 *   For all pairs of valid ISO-8601 date strings,
 *   sign(compareValues(a, b)) === sign(Date.parse(a) - Date.parse(b))
 *
 * Property 2 (Preservation):
 *   For all pairs of non-date values (numbers, plain strings, nullish),
 *   compareValues produces the same result as the original implementation.
 *
 * FINDING: For YYYY-MM-DD format, localeCompare happens to produce the same
 * ordering as chronological comparison because ISO-8601 was designed to be
 * lexicographically sortable. The bug is a semantic correctness issue —
 * compareValues uses string comparison instead of date comparison, which is
 * wrong in principle even though it produces correct results for this format.
 *
 * The test still validates the expected property: date strings must sort
 * chronologically. It will serve as a regression test after the fix.
 *
 * @see .kiro/specs/date-sorting-fix/bugfix.md — Requirements 1.1, 1.2, 2.1, 2.2
 * @see .kiro/specs/date-sorting-fix/bugfix.md — Requirements 3.1, 3.2, 3.3, 3.4, 3.5
 */

import fc from 'fast-check';
import { compareValues } from '../useTableSort';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Return -1, 0, or 1 matching the sign of n. */
const sign = (n: number): number => {
  if (n > 0) return 1;
  if (n < 0) return -1;
  return 0;
};

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/**
 * Generate a valid ISO-8601 date string in YYYY-MM-DD format.
 *
 * - Year:  1970–2099
 * - Month: 01–12
 * - Day:   01–28 (universally valid for all months)
 */
const isoDateArbitrary: fc.Arbitrary<string> = fc
  .tuple(
    fc.integer({ min: 1970, max: 2099 }),
    fc.integer({ min: 1, max: 12 }),
    fc.integer({ min: 1, max: 28 }),
  )
  .map(([year, month, day]) => {
    const y = String(year);
    const m = String(month).padStart(2, '0');
    const d = String(day).padStart(2, '0');
    return `${y}-${m}-${d}`;
  });

// ---------------------------------------------------------------------------
// Property 1: Bug Condition Exploration
// ---------------------------------------------------------------------------

describe('Property 1: Bug Condition — Date Strings Use localeCompare Instead of Chronological Comparison', () => {
  /**
   * For all (a, b) where both are ISO date strings:
   *   sign(compareValues(a, b)) === sign(Date.parse(a) - Date.parse(b))
   *
   * NOTE: On unfixed code, compareValues uses localeCompare for date strings.
   * For YYYY-MM-DD format, localeCompare coincidentally produces correct
   * chronological ordering because the format is lexicographically sortable
   * by design. The semantic bug (using string comparison instead of date
   * comparison) does not produce observable failures for this specific format.
   *
   * This test validates the expected behavior and will serve as a regression
   * test after the date comparison branch is added to compareValues.
   */
  it('compareValues sorts ISO date string pairs chronologically', () => {
    fc.assert(
      fc.property(isoDateArbitrary, isoDateArbitrary, (a, b) => {
        const actual = sign(compareValues(a, b));
        const expected = sign(Date.parse(a) - Date.parse(b));

        expect(actual).toBe(expected);
      }),
      { numRuns: 200 },
    );
  });
});


// ---------------------------------------------------------------------------
// Helpers — ISO date detection (mirrors the bug condition from bugfix.md)
// ---------------------------------------------------------------------------

/**
 * Detect whether a value is an ISO-8601 date string.
 * Used to filter date strings OUT of the preservation property domain.
 */
function isISODateString(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  if (!/^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$/.test(value)) return false;
  return Number.isFinite(Date.parse(value));
}

function isNullish(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

// ---------------------------------------------------------------------------
// Generators — Non-date cell values
// ---------------------------------------------------------------------------

/**
 * Generate a cell value: number, string, null, or undefined.
 * Weighted toward numbers and strings for meaningful sort comparisons.
 * Matches the pattern from useTableSort.property.test.ts.
 */
const cellValueArbitrary = fc.oneof(
  { weight: 3, arbitrary: fc.double({ min: -1e6, max: 1e6, noNaN: true }) },
  { weight: 3, arbitrary: fc.string({ minLength: 0, maxLength: 10 }) },
  { weight: 1, arbitrary: fc.constant(null) },
  { weight: 1, arbitrary: fc.constant(undefined) },
);

// ---------------------------------------------------------------------------
// Property 2: Preservation — Non-Date Values Sort Identically to Original
// ---------------------------------------------------------------------------

describe('Property 2: Preservation — Non-Date Values Sort Identically to Original', () => {
  /**
   * Observation step (documented baseline behavior on unfixed code):
   *
   * - compareValues(42, 17)          → 25        (numeric diff: a - b)
   * - compareValues("banana","apple") → positive  (localeCompare)
   * - compareValues(null, "hello")   → 1         (nullish sorts to end)
   * - compareValues("hello", null)   → -1        (non-nullish before nullish)
   * - compareValues(null, null)      → 0         (both nullish equal)
   * - compareValues(undefined, undefined) → 0    (both nullish equal)
   */

  /**
   * Property 2a: Number pairs — numeric comparison preserved.
   *
   * For all (a, b) where both are finite numbers:
   *   compareValues(a, b) === a - b
   *
   * Validates: Requirement 3.1
   */
  it('number pairs sort via numeric comparison (a - b)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true }),
        fc.double({ min: -1e6, max: 1e6, noNaN: true }),
        (a, b) => {
          const result = compareValues(a, b);
          expect(result).toBe(a - b);
        },
      ),
      { numRuns: 200 },
    );
  });

  /**
   * Property 2b: Plain string pairs — localeCompare preserved.
   *
   * For all (a, b) where both are non-date strings:
   *   compareValues(a, b) === String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })
   *
   * Validates: Requirement 3.2
   */
  it('plain string pairs sort via case-insensitive localeCompare', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 10 }),
        fc.string({ minLength: 0, maxLength: 10 }),
        (a, b) => {
          // Filter out ISO date strings — they belong to the bug condition domain
          fc.pre(!isISODateString(a) && !isISODateString(b));

          const result = compareValues(a, b);
          const expected = String(a).localeCompare(String(b), undefined, {
            sensitivity: 'base',
          });
          expect(result).toBe(expected);
        },
      ),
      { numRuns: 200 },
    );
  });

  /**
   * Property 2c: Nullish handling — nullish values sort to end.
   *
   * For all (a, b) where at least one is nullish:
   *   - Both nullish → 0
   *   - a nullish, b non-nullish → 1 (a sorts after b)
   *   - a non-nullish, b nullish → -1 (a sorts before b)
   *
   * Validates: Requirements 3.3, 3.4
   */
  it('nullish values sort to end (1/-1/0 per existing logic)', () => {
    fc.assert(
      fc.property(cellValueArbitrary, cellValueArbitrary, (a, b) => {
        // Only test pairs where at least one value is nullish
        fc.pre(isNullish(a) || isNullish(b));

        const result = compareValues(a, b);

        if (isNullish(a) && isNullish(b)) {
          expect(result).toBe(0);
        } else if (isNullish(a)) {
          expect(result).toBe(1);
        } else {
          // b is nullish
          expect(result).toBe(-1);
        }
      }),
      { numRuns: 200 },
    );
  });

  /**
   * Property 2d: General preservation — all non-date inputs produce
   * identical results to the known behavior patterns.
   *
   * For all (a, b) where neither is an ISO date string:
   *   compareValues(a, b) matches the expected branch:
   *   - Both nullish → 0
   *   - One nullish → 1 or -1
   *   - Both numbers → a - b
   *   - Otherwise → localeCompare
   *
   * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
   */
  it('all non-date inputs match original compareValues behavior', () => {
    fc.assert(
      fc.property(cellValueArbitrary, cellValueArbitrary, (a, b) => {
        // Exclude ISO date strings from the domain
        fc.pre(!isISODateString(a) && !isISODateString(b));

        const result = compareValues(a, b);

        // Reproduce the original compareValues logic to compute expected value
        const aNullish = isNullish(a);
        const bNullish = isNullish(b);

        if (aNullish && bNullish) {
          expect(result).toBe(0);
        } else if (aNullish) {
          expect(result).toBe(1);
        } else if (bNullish) {
          expect(result).toBe(-1);
        } else if (isFiniteNumber(a) && isFiniteNumber(b)) {
          expect(result).toBe(a - b);
        } else {
          const expected = String(a).localeCompare(String(b), undefined, {
            sensitivity: 'base',
          });
          expect(result).toBe(expected);
        }
      }),
      { numRuns: 200 },
    );
  });
});
