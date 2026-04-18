/**
 * Property-based tests for useFilterableTable hook
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Property 5
 */

import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useFilterableTable } from '../useFilterableTable';
import { useColumnFilters } from '../useColumnFilters';
import { useTableSort } from '../useTableSort';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a sort direction. */
const directionArbitrary = fc.constantFrom('asc' as const, 'desc' as const);

/** Generate a short alpha field name. */
const fieldNameArbitrary = fc.stringMatching(/^[a-z]{1,6}$/);

/** Generate a small set of column keys (1-4 keys, short alpha strings). */
const columnKeysArbitrary = fc
  .uniqueArray(fc.stringMatching(/^[a-z]{1,6}$/), { minLength: 1, maxLength: 4 })
  .filter((arr) => arr.length >= 1);

/**
 * Generate a cell value: number, string, null, or undefined.
 * Weighted toward strings for meaningful filter comparisons.
 */
const cellValueArbitrary = fc.oneof(
  { weight: 2, arbitrary: fc.double({ min: -1e6, max: 1e6, noNaN: true }) },
  { weight: 4, arbitrary: fc.string({ minLength: 0, maxLength: 8 }) },
  { weight: 1, arbitrary: fc.constant(null) },
  { weight: 1, arbitrary: fc.constant(undefined) },
);

/** Generate a row object with values for a given set of keys. */
const rowArbitrary = (keys: string[]) =>
  fc.record(
    Object.fromEntries(keys.map((k) => [k, cellValueArbitrary])),
    { requiredKeys: [] as string[] },
  ) as fc.Arbitrary<Record<string, any>>;

/** Generate filter values: short strings that could be substrings of field values. */
const filterValueArbitrary = fc.stringMatching(/^[a-zA-Z0-9]{0,4}$/);

// ---------------------------------------------------------------------------
// Property 5: Filter-Then-Sort Confluence
// ---------------------------------------------------------------------------

describe('Property 5: Filter-Then-Sort Confluence', () => {
  /**
   * **Validates: Requirements 3.3, 3.4, 12.5**
   *
   * For any data array, filter configuration, and sort configuration,
   * `processedData` from `useFilterableTable` is identical to independently
   * filtering the data with `useColumnFilters` and then sorting that filtered
   * result with `useTableSort`.
   */
  it('processedData equals independently filtering then sorting', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            fc.record(Object.fromEntries(keys.map((k) => [k, filterValueArbitrary]))),
            // Pick a sort field from the available keys
            fc.constantFrom(...keys),
            directionArbitrary,
          ),
        ),
        ([keys, data, filterValues, sortField, sortDirection]) => {
          jest.useFakeTimers();

          try {
            const initialFilters = Object.fromEntries(keys.map((k) => [k, '']));

            // --- Approach A: useFilterableTable (combined) ---
            const { result: combinedResult } = renderHook(() =>
              useFilterableTable(data, {
                initialFilters,
                defaultSort: { field: sortField, direction: sortDirection },
              }),
            );

            // Apply all filter values to the combined hook
            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                combinedResult.current.setFilter(key, value);
              }
            });
            act(() => {
              jest.advanceTimersByTime(200);
            });

            const combinedOutput = combinedResult.current.processedData;

            // --- Approach B: Independent filter then sort ---
            const { result: filterResult } = renderHook(() =>
              useColumnFilters(data, initialFilters),
            );

            // Apply same filter values
            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                filterResult.current.setFilter(key, value);
              }
            });
            act(() => {
              jest.advanceTimersByTime(200);
            });

            const filteredData = filterResult.current.filteredData;

            // Sort the filtered data independently
            const { result: sortResult } = renderHook(() =>
              useTableSort(filteredData, sortField, sortDirection),
            );

            const independentOutput = sortResult.current.sortedData;

            // --- Assert confluence ---
            expect(combinedOutput).toEqual(independentOutput);
          } finally {
            jest.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
