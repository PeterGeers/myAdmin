/**
 * Property-based tests for useTableSort hook
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Properties 3 & 4
 */

import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useTableSort } from '../useTableSort';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a sort direction. */
const directionArbitrary = fc.constantFrom('asc' as const, 'desc' as const);

/** Generate a short alpha field name. */
const fieldNameArbitrary = fc.stringMatching(/^[a-z]{1,6}$/);

/**
 * Generate a cell value: number, string, null, or undefined.
 * Weighted toward numbers and strings for meaningful sort comparisons.
 */
const cellValueArbitrary = fc.oneof(
  { weight: 3, arbitrary: fc.double({ min: -1e6, max: 1e6, noNaN: true }) },
  { weight: 3, arbitrary: fc.string({ minLength: 0, maxLength: 10 }) },
  { weight: 1, arbitrary: fc.constant(null) },
  { weight: 1, arbitrary: fc.constant(undefined) },
);

/** Generate a row object with a specific sort field plus optional extra fields. */
const rowWithFieldArbitrary = (sortField: string) =>
  fc.record({
    [sortField]: cellValueArbitrary,
    extra: fc.string({ minLength: 0, maxLength: 5 }),
  }) as fc.Arbitrary<Record<string, any>>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isNullish(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

// ---------------------------------------------------------------------------
// Property 3: Sort State Determinism
// ---------------------------------------------------------------------------

describe('Property 3: Sort State Determinism', () => {
  /**
   * **Validates: Requirements 2.3, 2.4, 2.5**
   *
   * For any current sort state and any field name:
   * - Same field toggles direction (asc↔desc)
   * - Different field resets to 'asc'
   * - getSortIndicator returns correct symbol for active/inactive fields
   */
  it('handleSort toggles or resets direction deterministically', () => {
    fc.assert(
      fc.property(
        fieldNameArbitrary,
        directionArbitrary,
        fieldNameArbitrary,
        (initialField, initialDirection, targetField) => {
          const data = [{ [initialField]: 'a' }, { [initialField]: 'b' }];

          const { result } = renderHook(() =>
            useTableSort(data, initialField, initialDirection),
          );

          // Verify initial state
          expect(result.current.sortField).toBe(initialField);
          expect(result.current.sortDirection).toBe(initialDirection);

          // Apply handleSort with targetField
          act(() => {
            result.current.handleSort(targetField);
          });

          if (targetField === initialField) {
            // Same field → direction toggled
            const expectedDirection = initialDirection === 'asc' ? 'desc' : 'asc';
            expect(result.current.sortField).toBe(initialField);
            expect(result.current.sortDirection).toBe(expectedDirection);
          } else {
            // Different field → new field, direction reset to 'asc'
            expect(result.current.sortField).toBe(targetField);
            expect(result.current.sortDirection).toBe('asc');
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('getSortIndicator returns correct symbol for active and inactive fields', () => {
    fc.assert(
      fc.property(
        fieldNameArbitrary,
        directionArbitrary,
        fieldNameArbitrary,
        (activeField, direction, queryField) => {
          const data = [{ [activeField]: 'x' }];

          const { result } = renderHook(() =>
            useTableSort(data, activeField, direction),
          );

          const indicator = result.current.getSortIndicator(queryField);

          if (queryField === activeField) {
            expect(indicator).toBe(direction === 'asc' ? '↑' : '↓');
          } else {
            expect(indicator).toBe('');
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Sort Ordering Correctness
// ---------------------------------------------------------------------------

describe('Property 4: Sort Ordering Correctness', () => {
  /**
   * **Validates: Requirements 2.6**
   *
   * For any data array, sort field, and direction, every consecutive pair
   * in sortedData respects the ordering:
   * - Strings case-insensitive
   * - Numbers numeric
   * - Null/undefined to end regardless of direction
   */
  it('every consecutive pair in sortedData respects the ordering', () => {
    fc.assert(
      fc.property(
        fieldNameArbitrary.chain((field) =>
          fc.tuple(
            fc.constant(field),
            fc.array(rowWithFieldArbitrary(field), { minLength: 0, maxLength: 30 }),
            directionArbitrary,
          ),
        ),
        ([sortField, data, direction]) => {
          const { result } = renderHook(() =>
            useTableSort(data, sortField, direction),
          );

          const sorted = result.current.sortedData;

          // Check every consecutive pair
          for (let i = 0; i < sorted.length - 1; i++) {
            const aVal = sorted[i][sortField];
            const bVal = sorted[i + 1][sortField];

            const aNullish = isNullish(aVal);
            const bNullish = isNullish(bVal);

            // Nullish values must be at the end
            if (aNullish && !bNullish) {
              // A nullish value before a non-nullish value → violation
              throw new Error(
                `Nullish value at index ${i} appears before non-nullish value at index ${i + 1}`,
              );
            }

            // If both non-nullish, check ordering
            if (!aNullish && !bNullish) {
              let cmp: number;

              if (isFiniteNumber(aVal) && isFiniteNumber(bVal)) {
                cmp = aVal - bVal;
              } else {
                cmp = String(aVal).localeCompare(String(bVal), undefined, {
                  sensitivity: 'base',
                });
              }

              if (direction === 'asc') {
                expect(cmp).toBeLessThanOrEqual(0);
              } else {
                expect(cmp).toBeGreaterThanOrEqual(0);
              }
            }

            // Both nullish → any order is fine
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('null/undefined values are always at the end of sortedData', () => {
    fc.assert(
      fc.property(
        fieldNameArbitrary.chain((field) =>
          fc.tuple(
            fc.constant(field),
            fc.array(rowWithFieldArbitrary(field), { minLength: 0, maxLength: 20 }),
            directionArbitrary,
          ),
        ),
        ([sortField, data, direction]) => {
          const { result } = renderHook(() =>
            useTableSort(data, sortField, direction),
          );

          const sorted = result.current.sortedData;
          const values = sorted.map((row) => row[sortField]);

          // Find the first nullish value
          const firstNullishIdx = values.findIndex((v) => isNullish(v));

          if (firstNullishIdx !== -1) {
            // All values from firstNullishIdx onward must be nullish
            for (let i = firstNullishIdx; i < values.length; i++) {
              expect(isNullish(values[i])).toBe(true);
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
