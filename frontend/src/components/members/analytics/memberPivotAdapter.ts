/**
 * Member Analytics — client-side pivot/list adapter (C4, D3 Option 2).
 *
 * The Members records live in DynamoDB behind the Members Lambda, while the
 * Dynamic Pivot Views framework aggregates server-side SQL over a registered
 * MySQL view. Rather than build a bespoke member pivot engine, this adapter
 * REUSES the framework's config / result / column-meta *shapes*
 * ({@link PivotConfig}, {@link PivotResult}, {@link PivotColumnMeta} from
 * `types/pivot.ts`) and performs the aggregation on the client over the page's
 * own scope-authorized, filtered `rows`. The produced {@link PivotResult} plugs
 * straight into the framework's existing `PivotResultTable` (design C4, ODI-3).
 *
 * `executeMemberPivot(rows, config, fieldConfig)`:
 *   - groups `rows` by `config.groupColumns`, reading each group key with the
 *     shared `valueFor(row, group, key)` accessor (nested storage bucket first,
 *     then flat) — the storage group is resolved from `fieldConfig.fields` so a
 *     fixed field under `personal`/`membership` and a flat overlay/calculated
 *     field both resolve (R4.1, R6.5);
 *   - computes each `config.aggregateMeasure` — COUNT / SUM / AVG / MIN / MAX —
 *     parsing numeric values via `toNumber` and EXCLUDING non-numeric inputs from
 *     SUM/AVG/MIN/MAX (COUNT counts rows, `*` or a column, consistent with SQL)
 *     (R4.7);
 *   - emits `columns` as {@link PivotColumnMeta} (one `group` entry per group
 *     column, one `aggregate` entry per measure);
 *   - when `groupColumns` is EMPTY → filtered-list mode (R4.8): returns one result
 *     row per member (projecting the measure target columns, or the full row when
 *     no measures are configured), NOT an aggregate.
 *
 * No label is hardcoded in English — a group column's result key is its field
 * `key` (config/fieldConfig-driven); aggregate column names are derived from the
 * SQL-style function + source column the caller configured. Localized display
 * labels are applied downstream by the result table from `fieldConfig`.
 *
 * Pure + unit-tested. No React, no I/O. Spec:
 * `.kiro/specs/Members/member-analytics` (design C4; R4.1, R4.7, R4.8, R5.3, R6.5).
 */
import type {
  AggregateFunction,
  AggregateMeasure,
  PivotColumnMeta,
  PivotConfig,
  PivotResult,
} from '../../../types/pivot';
import type { FieldConfig, FieldConfigField, MemberRow } from '../../../types/members';
import { valueFor } from '../fieldValue';
import { toNumber } from './memberAggregations';

/** The COUNT target sentinel (count rows, not a specific column). */
const COUNT_STAR = '*';

/**
 * Resolve the STORAGE group for a field key from the resolved field config, so
 * {@link valueFor} can read the nested bucket (`member[group][key]`) before the
 * flat fallback (`member[key]`). A key not present in `fieldConfig.fields`, or a
 * field with no `group`, resolves with `group === undefined` — `valueFor` then
 * reads the flat key directly, which is correct for overlay/calculated/flat-alias
 * fields.
 */
function groupForKey(fieldConfig: FieldConfig | undefined, key: string): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }
  const field: FieldConfigField | undefined = fields.find((f) => f?.key === key);
  return field?.group;
}

/**
 * Read a member value for `key` using the shared nested-or-flat `valueFor`
 * accessor, resolving the storage group from the field config first.
 */
function readValue(
  row: MemberRow,
  key: string,
  fieldConfig: FieldConfig | undefined,
): unknown {
  return valueFor(row, groupForKey(fieldConfig, key), key);
}

/**
 * The stable result-column name for an aggregate measure, mirroring the SQL
 * framework's convention (`FUNC(column)`, or `COUNT(*)`). Never English prose —
 * purely the configured function + source column, so the downstream table maps
 * it to a localized label from `fieldConfig`.
 */
export function aggregateColumnName(measure: AggregateMeasure): string {
  const column = measure.column || COUNT_STAR;
  return `${measure.function}(${column})`;
}

/**
 * Build the group-key string used to bucket a row. Multiple group columns are
 * joined on a unit-separator so distinct value tuples never collide. Absent
 * values bucket under the empty string (an "ungrouped"/blank group), never crash.
 */
function groupKeyFor(
  row: MemberRow,
  groupColumns: string[],
  fieldConfig: FieldConfig | undefined,
): string {
  return groupColumns
    .map((key) => {
      const v = readValue(row, key, fieldConfig);
      return v === null || v === undefined ? '' : String(v);
    })
    .join('\u241F');
}

/**
 * Compute a single aggregate function over a group's rows for one measure.
 *
 * - COUNT with `*` (or no column) counts the rows in the group.
 * - COUNT with a column counts rows whose value is present (non-null/undefined),
 *   mirroring SQL `COUNT(col)` which ignores NULLs.
 * - SUM / AVG / MIN / MAX parse each value via {@link toNumber} and operate over
 *   the PRESENT numeric values only; non-numeric inputs are excluded (never
 *   coerced to 0). An empty numeric set yields `0` for SUM and `null` for
 *   AVG/MIN/MAX (no meaningful average/extreme over zero values).
 */
function computeAggregate(
  fn: AggregateFunction,
  column: string,
  groupRows: MemberRow[],
  fieldConfig: FieldConfig | undefined,
): number | null {
  if (fn === 'COUNT') {
    if (!column || column === COUNT_STAR) {
      return groupRows.length;
    }
    let present = 0;
    for (const row of groupRows) {
      const v = readValue(row, column, fieldConfig);
      if (v !== null && v !== undefined && v !== '') {
        present += 1;
      }
    }
    return present;
  }

  // Numeric aggregates: parse + exclude non-numeric.
  const numbers: number[] = [];
  for (const row of groupRows) {
    const n = toNumber(readValue(row, column, fieldConfig));
    if (n !== null) {
      numbers.push(n);
    }
  }

  switch (fn) {
    case 'SUM':
      return numbers.reduce((acc, n) => acc + n, 0);
    case 'AVG':
      return numbers.length === 0
        ? null
        : numbers.reduce((acc, n) => acc + n, 0) / numbers.length;
    case 'MIN':
      return numbers.length === 0 ? null : Math.min(...numbers);
    case 'MAX':
      return numbers.length === 0 ? null : Math.max(...numbers);
    default:
      return null;
  }
}

/**
 * Build the {@link PivotColumnMeta} list for an aggregate result: one `group`
 * column per `groupColumns` entry, followed by one `aggregate` column per
 * measure. `dataType` is `string` for group keys (member values are rendered
 * as-is) and `decimal` for aggregates (numeric, locale-formatted downstream).
 */
function aggregateColumns(
  groupColumns: string[],
  measures: AggregateMeasure[],
): PivotColumnMeta[] {
  const groupMeta: PivotColumnMeta[] = groupColumns.map((name) => ({
    name,
    type: 'group',
    dataType: 'string',
  }));
  const measureMeta: PivotColumnMeta[] = measures.map((measure) => ({
    name: aggregateColumnName(measure),
    type: 'aggregate',
    dataType: 'decimal',
    function: measure.function,
    sourceColumn: measure.column || COUNT_STAR,
  }));
  return [...groupMeta, ...measureMeta];
}

/**
 * Filtered-list mode (R4.8): empty `groupColumns`. Returns one result row per
 * member — NOT an aggregate. When measures are configured, each result row
 * projects just those measure target columns (the chosen list columns); when no
 * measures are configured either, the full member row is returned untouched so
 * the caller can render whatever columns it chooses. The row ORDER and COUNT are
 * preserved exactly (one output row per input member) so scope + saved filters
 * are honored verbatim (R4.11 / R5.3 — the adapter never widens or drops rows).
 */
function filteredListResult(
  rows: MemberRow[],
  config: PivotConfig,
  fieldConfig: FieldConfig | undefined,
): PivotResult {
  // Column precedence (findings F-006/F-009):
  //   1. `config.listColumns` — the curated columns a preset / saved list set
  //      names (the fix: a list set shows meaningful member fields, not a dump);
  //   2. legacy: the measure target columns (a list set composed via the field
  //      picker as COUNT/… columns);
  //   3. fallback: project the config's MEANINGFUL fields (visible, non-system),
  //      NOT a raw `{ ...row }` dump (which leaked tenant_id/sk/overlay and
  //      rendered nested buckets as `[object Object]`).
  const curated = (config.listColumns ?? []).filter(
    (c): c is string => typeof c === 'string' && c !== '',
  );
  const measureCols = (config.aggregateMeasures ?? [])
    .map((m) => m.column)
    .filter((c): c is string => typeof c === 'string' && c !== '' && c !== COUNT_STAR);

  const columnKeys =
    curated.length > 0
      ? curated
      : measureCols.length > 0
        ? measureCols
        : meaningfulFieldKeys(fieldConfig);

  const data = rows.map((row) => {
    const projected: Record<string, unknown> = {};
    for (const key of columnKeys) {
      // Read nested-or-flat via valueFor so address/birthday/etc. resolve from
      // their storage bucket (never `[object Object]`); a key the tenant does
      // not expose simply renders blank.
      projected[key] = readValue(row, key, fieldConfig);
    }
    return projected;
  });

  const columns: PivotColumnMeta[] = columnKeys.map((name) => ({
    name,
    type: 'group',
    dataType: 'string',
  }));

  return { success: true, data, columns, row_count: data.length };
}

/**
 * System/internal keys that must NEVER appear as list columns (findings F-006):
 * storage/tenancy plumbing + the nested storage buckets themselves (which would
 * render as `[object Object]`). The curated preset columns and the config-driven
 * fallback both exclude these.
 */
const SYSTEM_LIST_KEYS = new Set<string>([
  'overlay',
  'personal',
  'membership',
  'scope_values',
  'tenant_id',
  'sk',
  'member_id',
  'membership_id',
  'region_display',
]);

/**
 * The meaningful member field keys for a full-projection filtered list — the
 * fallback when a list set names no columns (findings F-006). Instead of dumping
 * the raw row shape (system columns + `[object Object]` nested buckets), project
 * through the resolved field config: only VISIBLE, non-system fields, in config
 * order, each read via `valueFor` by the caller. An absent/empty config yields no
 * columns rather than a raw dump.
 */
function meaningfulFieldKeys(fieldConfig: FieldConfig | undefined): string[] {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return [];
  }
  const keys: string[] = [];
  for (const field of fields) {
    const key = field?.key;
    if (typeof key !== 'string' || key === '') continue;
    if (field?.visible === false) continue;
    if (SYSTEM_LIST_KEYS.has(key)) continue;
    if (!keys.includes(key)) keys.push(key);
  }
  return keys;
}

/**
 * Execute a member pivot/list set on the client (D3 Option 2).
 *
 * Groups `rows` by `config.groupColumns` and computes `config.aggregateMeasures`
 * (COUNT / SUM / AVG / MIN / MAX) when at least one group column is present; when
 * `groupColumns` is empty, runs in filtered-list mode (one row per member, R4.8).
 * Pure — no mutation of inputs, no I/O. The result conforms to the framework's
 * {@link PivotResult} so it renders through the existing `PivotResultTable`.
 */
export function executeMemberPivot(
  rows: MemberRow[],
  config: PivotConfig,
  fieldConfig: FieldConfig | undefined,
): PivotResult {
  const safeRows = Array.isArray(rows) ? rows : [];
  const groupColumns = Array.isArray(config?.groupColumns) ? config.groupColumns : [];
  const measures = Array.isArray(config?.aggregateMeasures) ? config.aggregateMeasures : [];

  // Filtered-list mode: no group-by (R4.8).
  if (groupColumns.length === 0) {
    return filteredListResult(safeRows, { ...config, aggregateMeasures: measures }, fieldConfig);
  }

  // Aggregate mode: bucket rows by the group-column value tuple, preserving the
  // first-seen group order so the result is deterministic.
  const buckets = new Map<string, { keyValues: unknown[]; rows: MemberRow[] }>();
  for (const row of safeRows) {
    const bucketKey = groupKeyFor(row, groupColumns, fieldConfig);
    let bucket = buckets.get(bucketKey);
    if (!bucket) {
      const keyValues = groupColumns.map((key) => readValue(row, key, fieldConfig));
      bucket = { keyValues, rows: [] };
      buckets.set(bucketKey, bucket);
    }
    bucket.rows.push(row);
  }

  const data: Record<string, unknown>[] = [];
  for (const bucket of buckets.values()) {
    const resultRow: Record<string, unknown> = {};
    groupColumns.forEach((key, i) => {
      const v = bucket.keyValues[i];
      resultRow[key] = v === undefined ? null : v;
    });
    for (const measure of measures) {
      resultRow[aggregateColumnName(measure)] = computeAggregate(
        measure.function,
        measure.column,
        bucket.rows,
        fieldConfig,
      );
    }
    data.push(resultRow);
  }

  return {
    success: true,
    data,
    columns: aggregateColumns(groupColumns, measures),
    row_count: data.length,
  };
}
