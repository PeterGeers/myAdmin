/**
 * useTableSort Hook
 *
 * Manages sort field, direction toggle, and applies sorting to a data array.
 * Replaces the ~15-line sort boilerplate pattern (useState for sort field/direction
 * + toggle handler) found in 7+ table components.
 *
 * @module hooks/useTableSort
 * @see .kiro/specs/table-filter-framework-v2/design.md §2
 */

import { useState, useMemo, useCallback } from 'react';
import { SortDirection } from '../components/filters/types';

interface UseTableSortReturn<T> {
  /** Currently active sort field, or null if no sort */
  sortField: string | null;
  /** Current sort direction */
  sortDirection: SortDirection;
  /** Toggle sort on a field (same field = flip direction, new field = asc) */
  handleSort: (field: string) => void;
  /** Data array after applying sort */
  sortedData: T[];
  /** Returns '↑', '↓', or '' for a given field */
  getSortIndicator: (field: string) => string;
}

/**
 * Check whether a value is a finite number (including numeric strings is NOT
 * considered — both values in a comparison must be actual numbers).
 */
function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Check whether a value is null or undefined.
 */
function isNullish(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

/**
 * Compare two values for sorting.
 *
 * Rules (from design §2):
 * - null/undefined sort to end regardless of direction
 * - Both numbers → numeric comparison
 * - Otherwise → case-insensitive string comparison via localeCompare
 *
 * Returns a raw comparator value (caller applies direction multiplier).
 */
function compareValues(a: unknown, b: unknown): number {
  const aNullish = isNullish(a);
  const bNullish = isNullish(b);

  // Both nullish → equal
  if (aNullish && bNullish) return 0;
  // Nullish values sort to end (regardless of direction — caller must handle)
  if (aNullish) return 1;
  if (bNullish) return -1;

  // Both numbers → numeric comparison
  if (isNumber(a) && isNumber(b)) {
    return a - b;
  }

  // Fallback → case-insensitive string comparison
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' });
}

/**
 * Hook for table column sorting with toggle behavior.
 *
 * @param data - The data array to sort
 * @param defaultField - Optional initial sort field
 * @param defaultDirection - Optional initial sort direction (default: 'asc')
 * @returns Sort state, handleSort, sortedData, getSortIndicator
 */
export function useTableSort<T extends Record<string, any>>(
  data: T[],
  defaultField?: string,
  defaultDirection?: SortDirection,
): UseTableSortReturn<T> {
  const [sortField, setSortField] = useState<string | null>(defaultField ?? null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(defaultDirection ?? 'asc');

  const handleSort = useCallback(
    (field: string) => {
      setSortField((prevField) => {
        if (prevField === field) {
          // Same field → toggle direction (handled below)
          return prevField;
        }
        // Different field → set new field, reset to asc
        return field;
      });
      setSortDirection((prevDirection) => {
        // We need to check current sortField to decide behavior.
        // Because setSortField above runs first in the same batch,
        // we read sortField from the ref-stable closure. However,
        // React may not have committed the setSortField yet.
        // Instead, compare against the *current* sortField state.
        if (sortField === field) {
          // Same field → toggle
          return prevDirection === 'asc' ? 'desc' : 'asc';
        }
        // Different field → reset to asc
        return 'asc';
      });
    },
    [sortField],
  );

  const getSortIndicator = useCallback(
    (field: string): string => {
      if (field !== sortField) return '';
      return sortDirection === 'asc' ? '↑' : '↓';
    },
    [sortField, sortDirection],
  );

  const sortedData = useMemo(() => {
    if (sortField === null) return data;

    const directionMultiplier = sortDirection === 'asc' ? 1 : -1;

    return [...data].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];

      // Nullish values always sort to end, regardless of direction
      const aNullish = isNullish(aVal);
      const bNullish = isNullish(bVal);
      if (aNullish && bNullish) return 0;
      if (aNullish) return 1;
      if (bNullish) return -1;

      return compareValues(aVal, bVal) * directionMultiplier;
    });
  }, [data, sortField, sortDirection]);

  return { sortField, sortDirection, handleSort, sortedData, getSortIndicator };
}
