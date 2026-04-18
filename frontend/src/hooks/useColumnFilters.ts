/**
 * useColumnFilters Hook
 *
 * Manages column filter state with debounce and case-insensitive substring matching.
 * Replaces the ~25-line boilerplate pattern (useState + useEffect debounce + useMemo filter)
 * found in 6+ table components.
 *
 * @module hooks/useColumnFilters
 * @see .kiro/specs/table-filter-framework-v2/design.md §1
 */

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { UseColumnFiltersOptions } from '../components/filters/types';

const DEFAULT_DEBOUNCE_MS = 150;

interface UseColumnFiltersReturn<T> {
  /** Current filter values keyed by column name */
  filters: Record<string, string>;
  /** Set a single filter value */
  setFilter: (key: string, value: string) => void;
  /** Reset all filters to empty strings */
  resetFilters: () => void;
  /** Data array after applying all active filters */
  filteredData: T[];
  /** True if any filter has a non-empty value */
  hasActiveFilters: boolean;
}

/**
 * Apply column filters to a data array.
 *
 * For each row, every non-empty filter is checked:
 * - If the filter key does not exist on the row, the filter passes (row not excluded).
 * - If the filter key exists, the row's field value (converted to string, lowercased)
 *   must contain the filter value (lowercased) for the row to pass.
 *
 * All active filters must pass for a row to be included (AND logic).
 */
function applyFilters<T extends Record<string, any>>(
  data: T[],
  filters: Record<string, string>,
): T[] {
  const activeFilters = Object.entries(filters).filter(([, v]) => v !== '');

  if (activeFilters.length === 0) {
    return data;
  }

  return data.filter((row) =>
    activeFilters.every(([key, filterValue]) => {
      if (!(key in row)) {
        return true; // missing field key → filter passes
      }
      const cellValue = row[key];
      return String(cellValue ?? '').toLowerCase().includes(filterValue.toLowerCase());
    }),
  );
}

/**
 * Hook for column-based text filtering with debounce.
 *
 * @param data - The data array to filter
 * @param initialFilters - Object whose keys define the filterable columns (values ignored; all start as '')
 * @param options - Optional configuration (debounceMs)
 * @returns Filter state, setFilter, resetFilters, filteredData, hasActiveFilters
 */
export function useColumnFilters<T extends Record<string, any>>(
  data: T[],
  initialFilters: Record<string, string>,
  options?: UseColumnFiltersOptions,
): UseColumnFiltersReturn<T> {
  const debounceMs = options?.debounceMs ?? DEFAULT_DEBOUNCE_MS;

  // Immediate filter state (for input binding)
  const [filters, setFilters] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.keys(initialFilters).map((key) => [key, ''])),
  );

  // Debounced filter state (for actual data filtering)
  const [debouncedFilters, setDebouncedFilters] = useState<Record<string, string>>(filters);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Set a single filter value: update immediately, debounce the data filtering
  const setFilter = useCallback(
    (key: string, value: string) => {
      setFilters((prev) => {
        const next = { ...prev, [key]: value };

        // Clear any pending debounce timer
        if (timerRef.current !== null) {
          clearTimeout(timerRef.current);
        }

        // Schedule debounced update
        timerRef.current = setTimeout(() => {
          setDebouncedFilters(next);
          timerRef.current = null;
        }, debounceMs);

        return next;
      });
    },
    [debounceMs],
  );

  // Reset all filters to empty strings
  const resetFilters = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const empty = Object.fromEntries(Object.keys(filters).map((key) => [key, '']));
    setFilters(empty);
    setDebouncedFilters(empty);
  }, [filters]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  // Compute filtered data from debounced filters
  const filteredData = useMemo(
    () => applyFilters(data, debouncedFilters),
    [data, debouncedFilters],
  );

  // hasActiveFilters checks the immediate filter state (not debounced)
  const hasActiveFilters = useMemo(
    () => Object.values(filters).some((v) => v !== ''),
    [filters],
  );

  return { filters, setFilter, resetFilters, filteredData, hasActiveFilters };
}
