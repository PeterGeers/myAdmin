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

// ---------------------------------------------------------------------------
// Member Analytics filter operators (data contract)
//
// Backward-compatible, operator-aware filter shape for the Member Analytics
// pivot/list saved-set `definition.filters`. OPAQUE to the SAM Members module
// and to the SQL pivot framework — both treat `PivotConfig.filters` as an
// untyped `Record<string, any>`. Only the member-analytics surface interprets
// an entry as a `FilterClause` (via `normalizeClause`).
// Reference: .kiro/specs/Members/member-analytics-pivot-filter-operators/design.md §"Data Models"
// ---------------------------------------------------------------------------

/**
 * The per-filter comparison operators. Type-adaptive availability is a UI
 * concern (`operatorsForField`); the engine implements semantics for all of
 * them regardless of field type.
 */
export type FilterOperator =
  | 'eq' // equals (case-insensitive, trimmed string compare) — the legacy default
  | 'ne' // not equals
  | 'gt' // greater than
  | 'gte' // greater than or equal
  | 'lt' // less than
  | 'lte' // less than or equal
  | 'contains' // substring (case-insensitive)
  | 'notContains' // does NOT contain substring — exact negation of `contains` for a present value
  | 'regex' // JS RegExp, case-insensitive default, invalid-pattern guarded
  | 'notRegex' // does NOT match the pattern (case-insensitive); same invalid-pattern guard as `regex`
  | 'empty' // field value is blank/absent (no value input)
  | 'notEmpty'; // field value is present/non-blank (no value input)

/** The set of known operators, used to clamp an unknown stored op to `eq`. */
const FILTER_OPERATORS: readonly FilterOperator[] = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'contains',
  'notContains',
  'regex',
  'notRegex',
  'empty',
  'notEmpty',
];

/** The new, explicit object form of a single filter entry. */
export interface FilterClause {
  op: FilterOperator;
  /** The comparison value as a string (as entered). Ignored for empty/notEmpty. */
  value?: string;
}

/**
 * The persisted member-analytics filters map. BACKWARD-COMPATIBLE and OPAQUE
 * to the backend:
 *   - new form:    { clubblad: { op: 'eq', value: 'Papier' } }
 *   - legacy form: { clubblad: 'Papier' }  (reads as { op: 'eq', value: 'Papier' })
 * A value may therefore be a `FilterClause` OR a legacy scalar; `unknown`-tolerant
 * readers (`normalizeClause`) accept both. NO key is special-cased — every entry,
 * including `years_member` / `joined_after_year`, is an ordinary filterable field
 * (a legacy scalar `years_member: 25` reads as an editable `{ op: 'eq', value: '25' }`
 * row, so a jubilee / new-member list is now expressible generically, e.g.
 * `years_member gte 25`).
 */
export type FilterMap = Record<string, FilterClause | string | number | null>;

/**
 * Read either the new object form or the legacy scalar form into a FilterClause.
 *   - legacy scalar  -> { op: 'eq', value: String(scalar) }
 *   - object with op -> clamped to a known FilterOperator (unknown op -> 'eq')
 *   - null/undefined -> null (caller treats as "no narrowing")
 *
 * Member-analytics reads of `PivotConfig.filters` go through this helper so the
 * richer structure stays opaque to the backend and the non-member pivot framework.
 */
export function normalizeClause(raw: unknown): FilterClause | null {
  if (raw === null || raw === undefined) {
    return null;
  }

  // Object (new) form: { op, value? }. Clamp an unknown/absent op to 'eq'.
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as { op?: unknown; value?: unknown };
    const op = FILTER_OPERATORS.includes(obj.op as FilterOperator)
      ? (obj.op as FilterOperator)
      : 'eq';
    const clause: FilterClause = { op };
    if (obj.value !== undefined && obj.value !== null) {
      clause.value = String(obj.value);
    }
    return clause;
  }

  // Legacy scalar form: the raw value is the eq comparison value.
  return { op: 'eq', value: String(raw) };
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
  /**
   * Filter values keyed by column or filter name.
   *
   * Kept as `Record<string, any>` so the SQL pivot framework (which also uses
   * `filters`) is unaffected. The Member Analytics surface treats this map as a
   * {@link FilterMap}: each entry is a {@link FilterClause} (`{ op, value? }`)
   * or a legacy scalar (`'Papier'` → `eq`), read via {@link normalizeClause}.
   * The structure stays OPAQUE to the backend and the non-member framework.
   */
  filters: Record<string, any>;
  /** Optional column whose distinct values become column headers */
  columnPivot: string | null;
  /** Additional columns for hierarchical column nesting (0–5) */
  columnNestLevels: string[];
  /** Whether to include WITH ROLLUP for hierarchical display */
  includeRollup?: boolean;
  /** Preferred display mode */
  displayMode: DisplayMode;
  /**
   * Member Analytics filtered-LIST column keys (findings F-006/F-009). For a
   * filtered-list set (`groupColumns` empty), these are the curated member field
   * keys the result projects — one column per key, read via the nested-or-flat
   * `valueFor` accessor by the client adapter. Absent/empty on an aggregate set.
   * Carried through the saved-set round-trip so a saved list set reruns with the
   * same columns. (Member-analytics-specific; the SQL framework ignores it.)
   */
  listColumns?: string[];
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
