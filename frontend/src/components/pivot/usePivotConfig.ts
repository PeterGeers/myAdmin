/**
 * usePivotConfig Hook
 *
 * Manages pivot configuration state: data source selection, column/measure
 * picking, filter values, display mode, and validation.
 *
 * Requirements: 1.1–1.8, 2.1–2.5, 9.1, 9.3, 9.5, 9.8, 9.10, 9.11
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import type {
  PivotConfig,
  AggregateMeasure,
  AggregateFunction,
  AvailableColumns,
  ColumnDef,
  PivotDataSource,
  DataSourceModule,
  DisplayMode,
} from '../../types/pivot';
import {
  getRegisteredSources,
  filterSourcesByModule,
  getAvailableColumns,
} from '../../services/pivotService';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const MAX_GROUP_COLUMNS = 5;
export const MAX_AGGREGATE_MEASURES = 10;
export const MAX_NEST_LEVELS = 5;

const AGGREGATE_FUNCTIONS: AggregateFunction[] = ['SUM', 'COUNT', 'AVG', 'MIN', 'MAX'];

const EMPTY_CONFIG: PivotConfig = {
  dataSource: '',
  groupColumns: [],
  aggregateMeasures: [],
  filters: {},
  columnPivot: null,
  columnNestLevels: [],
  includeRollup: false,
  displayMode: 'flat',
};

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

export interface ValidationErrors {
  groupColumns?: string;
  aggregateMeasures?: string;
  columnRoleOverlap?: string;
}

function validateConfig(config: PivotConfig): ValidationErrors {
  const errors: ValidationErrors = {};

  const groupColumns = config.groupColumns || [];
  const aggregateMeasures = config.aggregateMeasures || [];
  const columnNestLevels = config.columnNestLevels || [];

  if (groupColumns.length === 0) {
    errors.groupColumns = 'minGroupColumn';
  }
  if (aggregateMeasures.length === 0) {
    errors.aggregateMeasures = 'minAggregateMeasure';
  }

  // Check column role overlap — use plain object to avoid Map iteration issue
  const roles: Record<string, string[]> = {};
  for (const col of groupColumns) {
    roles[col] = [...(roles[col] || []), 'groupColumn'];
  }
  if (config.columnPivot) {
    roles[config.columnPivot] = [...(roles[config.columnPivot] || []), 'columnPivot'];
  }
  for (const col of columnNestLevels) {
    roles[col] = [...(roles[col] || []), 'nestLevel'];
  }
  for (const col of Object.keys(roles)) {
    if (roles[col].length > 1) {
      errors.columnRoleOverlap = col;
      break;
    }
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UsePivotConfigOptions {
  moduleFilter?: DataSourceModule | null;
  initialDataSource?: string;
}

export interface UsePivotConfigReturn {
  // Data sources
  dataSources: PivotDataSource[];
  dataSourcesLoading: boolean;

  // Available columns
  columns: AvailableColumns;
  columnsLoading: boolean;
  columnsError: string | null;

  // Config state
  config: PivotConfig;
  setConfig: (config: PivotConfig) => void;

  // Convenience setters
  setDataSource: (ds: string) => void;
  setGroupColumns: (cols: string[]) => void;
  addAggregateMeasure: () => void;
  removeAggregateMeasure: (index: number) => void;
  updateAggregateMeasure: (index: number, measure: AggregateMeasure) => void;
  setColumnPivot: (col: string | null) => void;
  setColumnNestLevels: (cols: string[]) => void;
  setDisplayMode: (mode: DisplayMode) => void;
  setIncludeRollup: (include: boolean) => void;
  setFilters: (filters: Record<string, any>) => void;
  updateFilter: (key: string, value: any) => void;

  // Derived state
  validation: ValidationErrors;
  isValid: boolean;
  aggregateFunctions: AggregateFunction[];

  // Column role exclusion helpers
  availableForGrouping: ColumnDef[];
  availableForPivot: ColumnDef[];
  availableForNesting: ColumnDef[];

  // Reset
  resetConfig: () => void;
}

export function usePivotConfig(options: UsePivotConfigOptions = {}): UsePivotConfigReturn {
  const { moduleFilter, initialDataSource } = options;

  // Data sources
  const [dataSources, setDataSources] = useState<PivotDataSource[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(true);

  // Available columns for selected data source
  const [columns, setColumns] = useState<AvailableColumns>({ groupable: [], aggregatable: [] });
  const [columnsLoading, setColumnsLoading] = useState(false);
  const [columnsError, setColumnsError] = useState<string | null>(null);

  // Pivot configuration
  const [config, setConfigState] = useState<PivotConfig>({
    ...EMPTY_CONFIG,
    dataSource: initialDataSource || '',
  });

  // -----------------------------------------------------------------------
  // Fetch data sources on mount
  // -----------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setDataSourcesLoading(true);
      try {
        const sources = await getRegisteredSources();
        if (!cancelled) {
          const filtered = filterSourcesByModule(sources, moduleFilter);
          setDataSources(filtered);
          // Auto-select initial data source if provided and available
          if (initialDataSource && filtered.some((s) => s.name === initialDataSource)) {
            setConfigState((prev) => ({ ...prev, dataSource: initialDataSource }));
          }
        }
      } catch {
        if (!cancelled) setDataSources([]);
      } finally {
        if (!cancelled) setDataSourcesLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [moduleFilter, initialDataSource]);

  // -----------------------------------------------------------------------
  // Fetch columns when data source changes
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!config.dataSource) {
      setColumns({ groupable: [], aggregatable: [] });
      return;
    }
    let cancelled = false;
    (async () => {
      setColumnsLoading(true);
      setColumnsError(null);
      try {
        const cols = await getAvailableColumns(config.dataSource);
        if (!cancelled) setColumns(cols);
      } catch (err) {
        if (!cancelled) {
          setColumnsError(err instanceof Error ? err.message : 'Failed to load columns');
          setColumns({ groupable: [], aggregatable: [] });
        }
      } finally {
        if (!cancelled) setColumnsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [config.dataSource]);

  // -----------------------------------------------------------------------
  // Setters
  // -----------------------------------------------------------------------
  const setConfig = useCallback((newConfig: PivotConfig) => {
    setConfigState(newConfig);
  }, []);

  const setDataSource = useCallback((ds: string) => {
    // Reset config when data source changes
    setConfigState({
      ...EMPTY_CONFIG,
      dataSource: ds,
    });
  }, []);

  const setGroupColumns = useCallback((cols: string[]) => {
    setConfigState((prev) => {
      const newConfig = { ...prev, groupColumns: cols.slice(0, MAX_GROUP_COLUMNS) };
      // Auto-set display mode
      if (cols.length >= 2 && prev.displayMode === 'flat') {
        newConfig.displayMode = 'hierarchical';
        newConfig.includeRollup = true;
      }
      if (cols.length < 2) {
        newConfig.displayMode = 'flat';
        newConfig.includeRollup = false;
      }
      return newConfig;
    });
  }, []);

  const addAggregateMeasure = useCallback(() => {
    setConfigState((prev) => {
      if (prev.aggregateMeasures.length >= MAX_AGGREGATE_MEASURES) return prev;
      return {
        ...prev,
        aggregateMeasures: [...prev.aggregateMeasures, { function: 'SUM', column: '' }],
      };
    });
  }, []);

  const removeAggregateMeasure = useCallback((index: number) => {
    setConfigState((prev) => ({
      ...prev,
      aggregateMeasures: prev.aggregateMeasures.filter((_, i) => i !== index),
    }));
  }, []);

  const updateAggregateMeasure = useCallback((index: number, measure: AggregateMeasure) => {
    setConfigState((prev) => ({
      ...prev,
      aggregateMeasures: prev.aggregateMeasures.map((m, i) => (i === index ? measure : m)),
    }));
  }, []);

  const setColumnPivot = useCallback((col: string | null) => {
    setConfigState((prev) => ({
      ...prev,
      columnPivot: col,
      // Clear nest levels when pivot is cleared
      columnNestLevels: col ? prev.columnNestLevels : [],
    }));
  }, []);

  const setColumnNestLevels = useCallback((cols: string[]) => {
    setConfigState((prev) => ({
      ...prev,
      columnNestLevels: cols.slice(0, MAX_NEST_LEVELS),
    }));
  }, []);

  const setDisplayMode = useCallback((mode: DisplayMode) => {
    setConfigState((prev) => ({
      ...prev,
      displayMode: mode,
      includeRollup: mode === 'hierarchical' ? true : prev.includeRollup,
    }));
  }, []);

  const setIncludeRollup = useCallback((include: boolean) => {
    setConfigState((prev) => ({ ...prev, includeRollup: include }));
  }, []);

  const setFilters = useCallback((filters: Record<string, any>) => {
    setConfigState((prev) => ({ ...prev, filters }));
  }, []);

  const updateFilter = useCallback((key: string, value: any) => {
    setConfigState((prev) => ({
      ...prev,
      filters: { ...prev.filters, [key]: value },
    }));
  }, []);

  const resetConfig = useCallback(() => {
    setConfigState(EMPTY_CONFIG);
  }, []);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------
  const validation = useMemo(() => validateConfig(config), [config]);
  const isValid = useMemo(
    () => Object.keys(validation).length === 0 && config.dataSource !== '',
    [validation, config.dataSource],
  );

  // Column role exclusion: a column used in one role is excluded from others
  const usedInGrouping = useMemo(() => new Set(config.groupColumns), [config.groupColumns]);
  const usedAsPivot = useMemo(() => (config.columnPivot ? new Set([config.columnPivot]) : new Set<string>()), [config.columnPivot]);
  const usedAsNesting = useMemo(() => new Set(config.columnNestLevels), [config.columnNestLevels]);

  const availableForGrouping = useMemo(
    () => columns.groupable.filter((c) => !usedAsPivot.has(c.name) && !usedAsNesting.has(c.name)),
    [columns.groupable, usedAsPivot, usedAsNesting],
  );

  const availableForPivot = useMemo(
    () => columns.groupable.filter((c) => !usedInGrouping.has(c.name) && !usedAsNesting.has(c.name)),
    [columns.groupable, usedInGrouping, usedAsNesting],
  );

  const availableForNesting = useMemo(
    () => columns.groupable.filter((c) => !usedInGrouping.has(c.name) && !usedAsPivot.has(c.name)),
    [columns.groupable, usedInGrouping, usedAsPivot],
  );

  return {
    dataSources,
    dataSourcesLoading,
    columns,
    columnsLoading,
    columnsError,
    config,
    setConfig,
    setDataSource,
    setGroupColumns,
    addAggregateMeasure,
    removeAggregateMeasure,
    updateAggregateMeasure,
    setColumnPivot,
    setColumnNestLevels,
    setDisplayMode,
    setIncludeRollup,
    setFilters,
    updateFilter,
    validation,
    isValid,
    aggregateFunctions: AGGREGATE_FUNCTIONS,
    availableForGrouping,
    availableForPivot,
    availableForNesting,
    resetConfig,
  };
}
