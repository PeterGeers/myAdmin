/**
 * Property-based tests for useFilterableTable hook
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Properties 3, 4, 5
 * @see .kiro/specs/budget-ui-alignment/design.md — Properties 3, 4
 */

import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useFilterableTable } from '../useFilterableTable';
import { useColumnFilters } from '../useColumnFilters';
import { useTableSort, compareValues } from '../useTableSort';

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
          vi.useFakeTimers();

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
              vi.advanceTimersByTime(200);
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
              vi.advanceTimersByTime(200);
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
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ---------------------------------------------------------------------------
// Property 3: Column filtering produces matching rows
// ---------------------------------------------------------------------------

describe('Property 3: Column filtering produces matching rows', () => {
  /**
   * **Validates: Requirements 3.6**
   *
   * For any dataset of budget rows and any non-empty filter string applied to a
   * column, all rows in the filtered output SHALL contain the filter string
   * (case-insensitive) in the value of that column.
   */
  it('all filtered rows contain the filter string in the target column', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            // Pick one column to filter on
            fc.constantFrom(...keys),
            // Non-empty filter value (at least 1 char)
            fc.stringMatching(/^[a-zA-Z0-9]{1,4}$/),
          ),
        ),
        ([keys, data, filterKey, filterValue]) => {
          vi.useFakeTimers();

          try {
            const initialFilters = Object.fromEntries(keys.map((k) => [k, '']));

            const { result } = renderHook(() =>
              useColumnFilters(data, initialFilters),
            );

            // Apply the filter
            act(() => {
              result.current.setFilter(filterKey, filterValue);
            });
            act(() => {
              vi.advanceTimersByTime(200);
            });

            const filtered = result.current.filteredData;

            // Property: every row in filtered output must contain the filter
            // string (case-insensitive) in the target column's value.
            // Exception: if the key is not present on the row, the filter passes.
            for (const row of filtered) {
              if (filterKey in row) {
                const cellStr = String(row[filterKey] ?? '').toLowerCase();
                expect(cellStr).toContain(filterValue.toLowerCase());
              }
            }
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Column sorting produces ordered output
// ---------------------------------------------------------------------------

describe('Property 4: Column sorting produces ordered output', () => {
  /**
   * **Validates: Requirements 3.7**
   *
   * For any dataset of budget rows and any sortable column, after applying a
   * sort in ascending direction, each consecutive pair of rows SHALL have the
   * sorted column value in non-decreasing order (and non-increasing for
   * descending). Nullish values always sort to end regardless of direction.
   */
  it('ascending sort produces non-decreasing order for consecutive pairs', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            fc.constantFrom(...keys),
          ),
        ),
        ([keys, data, sortField]) => {
          const { result } = renderHook(() =>
            useTableSort(data, sortField, 'asc'),
          );

          const sorted = result.current.sortedData;

          for (let i = 0; i < sorted.length - 1; i++) {
            const aVal = sorted[i][sortField];
            const bVal = sorted[i + 1][sortField];

            const aNullish = aVal === null || aVal === undefined;
            const bNullish = bVal === null || bVal === undefined;

            // Nullish values sort to end
            if (aNullish) {
              // If a is nullish, b must also be nullish (all nullish at end)
              expect(bNullish).toBe(true);
            } else if (!bNullish) {
              // Both non-nullish: a <= b (non-decreasing)
              expect(compareValues(aVal, bVal)).toBeLessThanOrEqual(0);
            }
            // If a is non-nullish and b is nullish, that's fine (nullish at end)
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('descending sort produces non-increasing order for consecutive pairs', () => {
    fc.assert(
      fc.property(
        columnKeysArbitrary.chain((keys) =>
          fc.tuple(
            fc.constant(keys),
            fc.array(rowArbitrary(keys), { minLength: 0, maxLength: 20 }),
            fc.constantFrom(...keys),
          ),
        ),
        ([keys, data, sortField]) => {
          const { result } = renderHook(() =>
            useTableSort(data, sortField, 'desc'),
          );

          const sorted = result.current.sortedData;

          for (let i = 0; i < sorted.length - 1; i++) {
            const aVal = sorted[i][sortField];
            const bVal = sorted[i + 1][sortField];

            const aNullish = aVal === null || aVal === undefined;
            const bNullish = bVal === null || bVal === undefined;

            // Nullish values sort to end
            if (aNullish) {
              expect(bNullish).toBe(true);
            } else if (!bNullish) {
              // Both non-nullish: a >= b (non-increasing)
              expect(compareValues(aVal, bVal)).toBeGreaterThanOrEqual(0);
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
