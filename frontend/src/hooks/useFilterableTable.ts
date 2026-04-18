/**
 * useFilterableTable Hook
 *
 * Composes `useColumnFilters` and `useTableSort` into a single interface for
 * components that need both column-based text filtering and sortable columns.
 * Filtering is applied before sorting so that sort operates only on the
 * filtered subset.
 *
 * @module hooks/useFilterableTable
 * @see .kiro/specs/table-filter-framework-v2/design.md §3
 */

import { useColumnFilters } from './useColumnFilters';
import { useTableSort } from './useTableSort';
import { SortDirection } from '../components/filters/types';

export interface UseFilterableTableConfig {
  /** Initial filter keys and empty values */
  initialFilters: Record<string, string>;
  /** Optional default sort configuration */
  defaultSort?: { field: string; direction: SortDirection };
  /** Optional debounce delay in milliseconds */
  debounceMs?: number;
}

export interface UseFilterableTableReturn<T> {
  // From useColumnFilters
  /** Current filter values keyed by column name */
  filters: Record<string, string>;
  /** Set a single filter value */
  setFilter: (key: string, value: string) => void;
  /** Reset all filters to empty strings */
  resetFilters: () => void;
  /** True if any filter has a non-empty value */
  hasActiveFilters: boolean;
  // From useTableSort
  /** Currently active sort field, or null if no sort */
  sortField: string | null;
  /** Current sort direction */
  sortDirection: SortDirection;
  /** Toggle sort on a field (same field = flip direction, new field = asc) */
  handleSort: (field: string) => void;
  /** Returns '↑', '↓', or '' for a given field */
  getSortIndicator: (field: string) => string;
  // Combined result
  /** Data after filtering then sorting */
  processedData: T[];
}

/**
 * Hook that composes column filtering and sorting for table components.
 *
 * Internally calls `useColumnFilters` on the raw data, then passes the
 * filtered output to `useTableSort`. The returned `processedData` is the
 * sorted-filtered result.
 *
 * @param data - The data array to filter and sort
 * @param config - Configuration with initialFilters, optional defaultSort, optional debounceMs
 * @returns Combined filter + sort state and processedData
 */
export function useFilterableTable<T extends Record<string, any>>(
  data: T[],
  config: UseFilterableTableConfig,
): UseFilterableTableReturn<T> {
  // Step 1: Filter the data
  const {
    filters,
    setFilter,
    resetFilters,
    filteredData,
    hasActiveFilters,
  } = useColumnFilters(data, config.initialFilters, {
    debounceMs: config.debounceMs,
  });

  // Step 2: Sort the filtered output (not the original data)
  const {
    sortField,
    sortDirection,
    handleSort,
    sortedData,
    getSortIndicator,
  } = useTableSort(filteredData, config.defaultSort?.field, config.defaultSort?.direction);

  return {
    // From useColumnFilters
    filters,
    setFilter,
    resetFilters,
    hasActiveFilters,
    // From useTableSort
    sortField,
    sortDirection,
    handleSort,
    getSortIndicator,
    // Combined result: sorted output of filtered data
    processedData: sortedData,
  };
}
