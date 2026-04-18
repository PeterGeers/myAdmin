/**
 * useTableConfig Hook
 *
 * Reads table column configuration from the parameter system for complex CRUD
 * tables. Follows the same pattern as `useFieldConfig` for form fields.
 *
 * Scope: ChartOfAccounts, ParameterManagement, BankingProcessor mutaties tab.
 *
 * @module hooks/useTableConfig
 * @see .kiro/specs/table-filter-framework-v2/design.md §5
 */

import { useState, useEffect, useCallback } from 'react';
import { getParameters } from '../services/parameterService';
import { SortDirection } from '../components/filters/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TableConfig {
  /** Ordered array of visible column keys */
  columns: string[];
  /** Column keys that get a FilterableHeader filter input */
  filterableColumns: string[];
  /** Default sort configuration */
  defaultSort: { field: string; direction: SortDirection };
  /** Number of rows per page */
  pageSize: number;
  /** Loading state */
  loading: boolean;
  /** Error message, if any */
  error: string | null;
}

export type TableEntity = 'chart_of_accounts' | 'parameters' | 'banking_mutaties';

// ---------------------------------------------------------------------------
// Hardcoded defaults (used when no parameter exists at any scope)
// ---------------------------------------------------------------------------

type TableConfigDefaults = Omit<TableConfig, 'loading' | 'error'>;

export const DEFAULTS: Record<TableEntity, TableConfigDefaults> = {
  chart_of_accounts: {
    columns: [
      'Account', 'AccountName', 'AccountLookup', 'SubParent',
      'Parent', 'VW', 'Belastingaangifte', 'parameters',
    ],
    filterableColumns: [
      'Account', 'AccountName', 'AccountLookup', 'SubParent',
      'Parent', 'VW', 'Belastingaangifte', 'parameters',
    ],
    defaultSort: { field: 'Account', direction: 'asc' },
    pageSize: 1000,
  },
  parameters: {
    columns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    filterableColumns: ['namespace', 'key', 'value', 'value_type', 'scope_origin'],
    defaultSort: { field: 'namespace', direction: 'asc' },
    pageSize: 100,
  },
  banking_mutaties: {
    columns: [
      'ID', 'TransactionNumber', 'TransactionDate', 'TransactionDescription',
      'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber',
      'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration',
    ],
    filterableColumns: [
      'ID', 'TransactionNumber', 'TransactionDate', 'TransactionDescription',
      'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber',
      'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration',
    ],
    defaultSort: { field: 'TransactionDate', direction: 'desc' },
    pageSize: 100,
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Safely parse a JSON parameter value, returning `undefined` on failure.
 */
function safeParseJson<T>(value: any): T | undefined {
  if (value === null || value === undefined) return undefined;
  try {
    return typeof value === 'string' ? JSON.parse(value) : value;
  } catch {
    return undefined;
  }
}

/**
 * Validate that a parsed value is a non-empty string array.
 */
function isNonEmptyStringArray(val: unknown): val is string[] {
  return Array.isArray(val) && val.length > 0 && val.every((v) => typeof v === 'string');
}

/**
 * Validate that a parsed value is a valid SortConfig.
 */
function isValidSortConfig(val: unknown): val is { field: string; direction: SortDirection } {
  if (typeof val !== 'object' || val === null) return false;
  const obj = val as Record<string, unknown>;
  return (
    typeof obj.field === 'string' &&
    obj.field.length > 0 &&
    (obj.direction === 'asc' || obj.direction === 'desc')
  );
}

/**
 * Validate that a parsed value is a positive number.
 */
function isPositiveNumber(val: unknown): val is number {
  return typeof val === 'number' && val > 0 && Number.isFinite(val);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetches table configuration from the parameter system for a given entity.
 *
 * Returns hardcoded defaults immediately while loading, and merges any
 * parameter overrides found at tenant or system scope. Falls back to
 * defaults on error without breaking table rendering.
 *
 * @param entity - The table entity identifier
 * @returns TableConfig with columns, filterableColumns, defaultSort, pageSize, loading, error
 */
export function useTableConfig(entity: TableEntity): TableConfig {
  const defaults = DEFAULTS[entity];

  const [config, setConfig] = useState<TableConfigDefaults>(defaults);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const resp = await getParameters('ui.tables');

      if (!resp.success) {
        console.error(`Failed to load table config for ${entity}: API returned success=false`);
        setError('Failed to load table configuration');
        setConfig(defaults);
        return;
      }

      // Parameters are grouped by namespace; we need the 'ui.tables' group
      const params = resp.parameters?.['ui.tables'] ?? [];

      // Build a lookup: key → resolved value
      const paramMap = new Map<string, any>();
      for (const param of params) {
        paramMap.set(param.key, param.value);
      }

      // Merge parameter overrides with defaults
      const columnsRaw = safeParseJson<string[]>(paramMap.get(`${entity}.columns`));
      const filterableRaw = safeParseJson<string[]>(paramMap.get(`${entity}.filterable_columns`));
      const sortRaw = safeParseJson<{ field: string; direction: SortDirection }>(
        paramMap.get(`${entity}.default_sort`),
      );
      const pageSizeRaw = safeParseJson<number>(paramMap.get(`${entity}.page_size`));

      setConfig({
        columns: isNonEmptyStringArray(columnsRaw) ? columnsRaw : defaults.columns,
        filterableColumns: isNonEmptyStringArray(filterableRaw) ? filterableRaw : defaults.filterableColumns,
        defaultSort: isValidSortConfig(sortRaw) ? sortRaw : defaults.defaultSort,
        pageSize: isPositiveNumber(pageSizeRaw) ? pageSizeRaw : defaults.pageSize,
      });
    } catch (err) {
      console.error(`Failed to fetch table config for ${entity}:`, err);
      setError('Failed to load table configuration');
      setConfig(defaults);
    } finally {
      setLoading(false);
    }
  }, [entity, defaults]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return {
    ...config,
    loading,
    error,
  };
}
