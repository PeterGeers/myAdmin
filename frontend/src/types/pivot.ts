/**
 * Pivot View Types
 *
 * Type definitions for the Dynamic Pivot Views feature.
 * Covers data source metadata, pivot configuration, query results,
 * saved model definitions, and display preferences.
 *
 * Requirements: 1.3, 1.4, 1.5, 11.6, 11.7
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4, §5, §6
 */

// ---------------------------------------------------------------------------
// Data source types
// ---------------------------------------------------------------------------

/** Module tags for data source routing (e.g. 'FIN', 'STR', 'ZZP', 'ADMIN'). Open string so new modules can be added on the backend without changing this type. */
export type DataSourceModule = string;

/** A registered pivot data source returned by GET /api/pivot/sources */
export interface PivotDataSource {
  /** Database view/table name (e.g. 'vw_mutaties') */
  name: string;
  /** Human-readable label (e.g. 'Financial Transactions') */
  label: string;
  /** Module tag for UI routing, or null if unassigned */
  module: DataSourceModule | null;
}

/**
 * Frontend data source configuration.
 * Describes a registered data source for the PivotBuilder dropdown
 * and which filter components to render.
 */
export interface DataSourceConfig {
  /** Database view/table name (e.g. 'vw_mutaties') */
  key: string;
  /** Human-readable label (e.g. 'Financial Transactions') */
  label: string;
  /** Configuration for which filter components to render and their props */
  filterConfig: FilterConfig;
}

/** Filter configuration for a data source */
export interface FilterConfig {
  /** Filter keys supported by this data source */
  filterKeys: string[];
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

/** A single column definition returned by GET /api/pivot/columns/<source> */
export interface ColumnDef {
  /** Column name in the database (e.g. 'Aangifte') */
  name: string;
  /** SQL data type (e.g. 'varchar', 'decimal', 'int') */
  type: string;
  /** Human-readable label */
  label: string;
}

/** Available columns for a data source, split by role */
export interface AvailableColumns {
  /** Columns available for GROUP BY */
  groupable: ColumnDef[];
  /** Columns available for aggregation (SUM, COUNT, etc.) */
  aggregatable: ColumnDef[];
}

// ---------------------------------------------------------------------------
// Pivot configuration
// ---------------------------------------------------------------------------

/** Supported aggregation functions */
export type AggregateFunction = 'SUM' | 'COUNT' | 'AVG' | 'MIN' | 'MAX';

/** A single aggregate measure: function + target column */
export interface AggregateMeasure {
  /** Aggregation function to apply */
  function: AggregateFunction;
  /** Target column name (or '*' for COUNT) */
  column: string;
}

/** Display mode for the result table */
export type DisplayMode = 'flat' | 'hierarchical';

/** Number formatting mode for aggregate values */
export type NumberFormat = 'decimal' | 'whole' | 'k-notation';

/** Complete pivot view configuration sent to POST /api/pivot/execute */
export interface PivotConfig {
  /** Data source to query (e.g. 'vw_mutaties') */
  dataSource: string;
  /** Columns to group by (1–5) */
  groupColumns: string[];
  /** Aggregate measures to compute (1–10) */
  aggregateMeasures: AggregateMeasure[];
  /** Filter values keyed by column or filter name */
  filters: Record<string, any>;
  /** Optional column whose distinct values become column headers */
  columnPivot: string | null;
  /** Additional columns for hierarchical column nesting (0–5) */
  columnNestLevels: string[];
  /** Whether to include WITH ROLLUP for hierarchical display */
  includeRollup?: boolean;
  /** Preferred display mode */
  displayMode: DisplayMode;
}

// ---------------------------------------------------------------------------
// Pivot query results
// ---------------------------------------------------------------------------

/** Metadata for a single column in the pivot result */
export interface PivotColumnMeta {
  /** Column name in the result set */
  name: string;
  /** Column role: 'group' or 'aggregate' */
  type: 'group' | 'aggregate';
  /** SQL data type (e.g. 'varchar', 'decimal', 'int') */
  dataType: string;
  /** Aggregation function used (only for aggregate columns) */
  function?: AggregateFunction;
  /** Source column name (only for aggregate columns) */
  sourceColumn?: string;
  /** Pivot value this column belongs to (only for pivoted aggregate columns) */
  pivotValue?: string | number;
  /** Name of the column used as pivot (only for pivoted aggregate columns) */
  pivotColumn?: string;
  /** Nest level values for hierarchical column headers (only for pivoted columns with nest levels) */
  nestValues?: Record<string, string | number>;
  /** Pivot group: 'pivot' for pivoted columns, 'total' for grand total columns */
  pivotGroup?: 'pivot' | 'total';
}

/** Response from POST /api/pivot/execute */
export interface PivotResult {
  success: boolean;
  /** Result rows as key-value objects */
  data: Record<string, any>[];
  /** Column metadata describing each column in the result */
  columns: PivotColumnMeta[];
  /** Total number of rows returned */
  row_count: number;
  /** Error message (present when success is false) */
  error?: string;
}

// ---------------------------------------------------------------------------
// Saved pivot models
// ---------------------------------------------------------------------------

/** Summary of a saved pivot model (from GET /api/pivot/models list) */
export interface PivotModelSummary {
  id: number;
  name: string;
  data_source: string;
  created_by: string;
  created_at: string;
}

/** Full saved pivot model (from GET /api/pivot/models/<id>) */
export interface PivotModel {
  id: number;
  name: string;
  data_source: string;
  definition: PivotConfig;
  created_by: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// API response wrappers
// ---------------------------------------------------------------------------

/** Generic success/error response from pivot API */
export interface PivotApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}

/** Response from POST /api/pivot/models (save) */
export interface SaveModelResponse {
  success: boolean;
  id?: number;
  error?: string;
}

/** Response from POST /api/pivot/export */
export interface ExportResponse {
  success: boolean;
  data: Record<string, any>[];
  row_count: number;
  error?: string;
}
