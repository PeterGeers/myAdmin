/**
 * Property-based tests for useColumnFilters hook
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Properties 1 & 2
 */

import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useColumnFilters } from '../useColumnFilters';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a row object with string-valued fields from a given set of keys. */
const rowArbitrary = (keys: string[]) =>
  fc.record(
    Object.fromEntries(keys.map((k) => [k, fc.oneof(fc.string(), fc.constant(undefined))])),
    { requiredKeys: [] as string[] },
  ) as fc.Arbitrary<Record<string, any>>;

/** Generate a small set of column keys (1-4 keys, short alpha strings). */
const columnKeysArbitrary = fc
  .uniqueArray(fc.stringMatching(/^[a-z]{1,6}$/), { minLength: 1, maxLength: 4 })
  .filter((arr) => arr.length >= 1);

/** Generate filter values: short strings that could be substrings of field values. */
const filterValueArbitrary = fc.stringMatching(/^[a-zA-Z0-9]{0,4}$/);

// ---------------------------------------------------------------------------
// Property 1: Filter Correctness
// ---------------------------------------------------------------------------

describe('Property 1: Filter Correctness', () => {
  /**
   * **Validates: Requirements 1.4, 1.5**
   *
   * For any data array and any set of column filter strings, filtered output
   * contains exactly those rows where every active filter key either does not
   * exist on the row or the row's field value (lowercase string) contains the
   * filter value (lowercase substring).
   */
  it('filtered output matches the filter predicate for all inputs', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            fc.record(Object.fromEntries(keys.map((k) => [k, filterValueArbitrary]))),
          ),
        ),
        ([keys, data, filterValues]) => {
          jest.useFakeTimers();

          try {
            const initialFilters = Object.fromEntries(keys.map((k) => [k, '']));

            const { result } = renderHook(() =>
              useColumnFilters(data, initialFilters),
            );

            // Apply all filter values
            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                result.current.setFilter(key, value);
              }
            });

            // Advance past debounce
            act(() => {
              jest.advanceTimersByTime(200);
            });

            const filtered = result.current.filteredData;

            // Compute expected result using the same predicate from the spec
            const activeFilters = Object.entries(filterValues).filter(([, v]) => v !== '');
            const expected = data.filter((row) =>
              activeFilters.every(([key, filterValue]) => {
                if (!(key in row)) return true;
                return String(row[key] ?? '')
                  .toLowerCase()
                  .includes(filterValue.toLowerCase());
              }),
            );

            expect(filtered).toEqual(expected);
          } finally {
            jest.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Filter Reset Round-Trip
// ---------------------------------------------------------------------------

describe('Property 2: Filter Reset Round-Trip', () => {
  /**
   * **Validates: Requirements 1.6, 12.6**
   *
   * For any data array and any set of active filter values, calling
   * `resetFilters` then reading `filteredData` returns array identical to
   * original unfiltered data (same elements, same order).
   */
  it('resetFilters restores filteredData to the original data array', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            fc.record(Object.fromEntries(keys.map((k) => [k, filterValueArbitrary]))),
          ),
        ),
        ([keys, data, filterValues]) => {
          jest.useFakeTimers();

          try {
            const initialFilters = Object.fromEntries(keys.map((k) => [k, '']));

            const { result } = renderHook(() =>
              useColumnFilters(data, initialFilters),
            );

            // Apply filters
            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                result.current.setFilter(key, value);
              }
            });
            act(() => {
              jest.advanceTimersByTime(200);
            });

            // Reset filters
            act(() => {
              result.current.resetFilters();
            });

            // After reset, filteredData should be identical to original data
            expect(result.current.filteredData).toEqual(data);
          } finally {
            jest.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
