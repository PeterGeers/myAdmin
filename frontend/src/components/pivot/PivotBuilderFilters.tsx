/**
 * PivotBuilderFilters Component
 *
 * Dynamically renders a search filter for every groupable column returned by
 * the AllowedColumnsRegistry. No hardcoded data-source logic — the available
 * columns are fully driven by the backend's `getAvailableColumns()` response
 * and the parameter-based column restrictions.
 *
 * Each groupable column gets a text input. The user types a value (or
 * comma-separated values for multi-value filtering) and the backend applies
 * them as parameterized WHERE conditions. The backend silently ignores
 * unknown column names, so this component can safely send any column key.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import React, { useMemo } from 'react';
import { Box, Text } from '@chakra-ui/react';
import { FilterPanel } from '../filters/FilterPanel';
import type { SearchFilterConfig } from '../filters/types';
import type { ColumnDef } from '../../types/pivot';

export interface PivotBuilderFiltersProps {
  /** Groupable columns for the selected data source (from getAvailableColumns) */
  groupableColumns: ColumnDef[];
  /** Current filter values keyed by column name */
  filters: Record<string, any>;
  /** Callback when a filter value changes — key is the column name */
  onFilterChange: (columnName: string, value: any) => void;
  /** Translation function */
  t: (key: string, options?: Record<string, any>) => string;
  /** Whether filters are disabled (e.g. while columns are loading) */
  disabled?: boolean;
}

/**
 * Build a search filter config for each groupable column.
 *
 * Every groupable column becomes a text search input. The user can type a
 * single value or comma-separated values. The backend's _build_where_clause
 * handles both scalar and list filter values automatically.
 */
function buildFilterConfigs(
  groupableColumns: ColumnDef[],
  filters: Record<string, any>,
  onFilterChange: (key: string, value: any) => void,
): SearchFilterConfig[] {
  return groupableColumns.map((col) => ({
    type: 'search' as const,
    label: col.label || col.name,
    value: filters[col.name] != null ? String(filters[col.name]) : '',
    onChange: (val: string) => {
      // If the value contains commas, split into an array for multi-value IN filtering
      const trimmed = val.trim();
      if (!trimmed) {
        onFilterChange(col.name, null);
        return;
      }
      if (trimmed.includes(',')) {
        const parts = trimmed
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        onFilterChange(col.name, parts.length > 1 ? parts : parts[0] || null);
      } else {
        onFilterChange(col.name, trimmed);
      }
    },
    placeholder: col.label || col.name,
  }));
}

export function PivotBuilderFilters({
  groupableColumns,
  filters,
  onFilterChange,
  t,
  disabled = false,
}: PivotBuilderFiltersProps): React.ReactElement | null {
  const filterConfigs = useMemo(
    () => buildFilterConfigs(groupableColumns, filters, onFilterChange),
    [groupableColumns, filters, onFilterChange],
  );

  if (filterConfigs.length === 0) return null;

  return (
    <Box>
      <Text fontSize="sm" color="gray.400" mb={2}>
        {t('pivot.builder.filters') ?? 'Filters'}
        <Text as="span" fontSize="xs" color="gray.500" ml={2}>
          ({t('pivot.builder.filtersHint') ?? 'use commas for multiple values'})
        </Text>
      </Text>
      <FilterPanel
        filters={filterConfigs}
        layout="grid"
        gridColumns={4}
        gridMinWidth="160px"
        size="sm"
        spacing={3}
        disabled={disabled}
        labelColor="white"
        bg="gray.600"
        color="white"
      />
    </Box>
  );
}

export default PivotBuilderFilters;
