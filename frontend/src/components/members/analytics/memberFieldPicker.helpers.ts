/**
 * memberFieldPicker.helpers — the PURE, framework-free transforms behind {@link MemberFieldPicker}.
 *
 * The field-picker modal composes a {@link PivotConfig} from the resolved field config. The
 * label resolution, the measure/filter draft round-tripping, and the pickable-field / list-column
 * derivation are all pure data transforms with NO React / Chakra dependency, so they live apart
 * from the modal component along a clean cohesion seam and are unit-testable in isolation. The
 * component imports them; nothing outside the component needs them, so they are NOT re-exported
 * through `MemberFieldPicker.tsx` (its public surface — `MemberFieldPicker`,
 * `MEMBER_PIVOT_DATA_SOURCE`, `PivotSeed`, `ExistingPivotModel`, `MemberFieldPickerProps` — is
 * unchanged).
 *
 * @module components/members/analytics/memberFieldPicker.helpers
 */

import type {
  FieldConfig,
  FieldConfigField,
  LocalizedLabel,
} from '../../../types/members';
import type {
  AggregateFunction,
  AggregateMeasure,
  FilterOperator,
  PivotConfig,
} from '../../../types/pivot';
import { normalizeClause } from '../../../types/pivot';
import { operatorTakesNoValue } from './analyticsConfig';

/** The aggregate functions the framework supports (mirrors `AggregateFunction`). */
export const AGGREGATE_FUNCTIONS: readonly AggregateFunction[] = [
  'COUNT',
  'SUM',
  'AVG',
  'MIN',
  'MAX',
];

/** The COUNT(*) sentinel — count all rows in a group, not a specific column. */
export const COUNT_STAR = '*';

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language,
 * mirroring the Members table's `fieldForm.resolveLabel` (prefer active language,
 * then `nl`, then `en`, then the fallback). Kept local so the analytics surface
 * has no cross-module import of a form helper (R4.5 / R6.1).
 */
export function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/** A single composable aggregate-measure row in local state (stable id for React keys). */
export interface MeasureDraft {
  id: string;
  function: AggregateFunction;
  /** Field key, or `''` meaning COUNT(*) (all rows). */
  column: string;
}

let measureIdSeq = 0;
export function nextMeasureId(): string {
  measureIdSeq += 1;
  return `measure-${measureIdSeq}`;
}

/** Turn a config's `aggregateMeasures` into editable `MeasureDraft`s. */
export function toDrafts(measures: AggregateMeasure[] | undefined): MeasureDraft[] {
  return (measures ?? []).map((m) => ({
    id: nextMeasureId(),
    function: m.function,
    column: m.column === COUNT_STAR ? '' : m.column,
  }));
}

/** Turn editable `MeasureDraft`s back into framework `AggregateMeasure`s. */
export function fromDrafts(drafts: MeasureDraft[]): AggregateMeasure[] {
  return drafts.map((d) => ({
    function: d.function,
    column: d.function === 'COUNT' && d.column === '' ? COUNT_STAR : d.column,
  }));
}

/** A single composable definition-filter row in local state (stable id for React keys). */
export interface FilterDraft {
  id: string;
  /** Field key the filter matches on, or `''` (unset row). */
  field: string;
  /** The operator for this row (defaults to `eq`). */
  op: FilterOperator;
  /** The comparison value (string). Empty/unused for `empty` / `notEmpty`. */
  value: string;
}

let filterIdSeq = 0;
export function nextFilterId(): string {
  filterIdSeq += 1;
  return `filter-${filterIdSeq}`;
}

/**
 * Seed the editable filter rows from a config's `filters` map. EVERY non-null
 * entry becomes an editable row — no key is special-cased, so a legacy scalar
 * `years_member: 25` reads as an ordinary editable `{ op: 'eq', value: '25' }`
 * row (R8.5 / R8.9). Each entry is read through {@link normalizeClause}, which
 * accepts both the legacy scalar form (`{ k: 'Papier' }` → `{ op: 'eq', value:
 * 'Papier' }`) and the new object form (`{ k: { op, value? } }`, unknown op
 * clamped to `eq`). `null` / `undefined` entries are skipped (no narrowing).
 * A clause's `value` is stringified for the text input (`''` when absent).
 */
export function toFilterDrafts(
  filters: Record<string, unknown> | undefined,
): FilterDraft[] {
  if (!filters) return [];
  const drafts: FilterDraft[] = [];
  for (const [field, raw] of Object.entries(filters)) {
    const clause = normalizeClause(raw);
    if (clause === null) {
      continue; // null/undefined entry → no narrowing
    }
    drafts.push({
      id: nextFilterId(),
      field,
      op: clause.op,
      value: clause.value ?? '',
    });
  }
  return drafts;
}

/**
 * Compose the editable filter rows into the persisted {@link FilterClause} map,
 * built PURELY from the editor rows (there is no reserved-key carry — every
 * key is an ordinary editable row, so nothing is carried through from an
 * external base).
 *
 * Each kept row emits the object form `{ op, value? }`, with `value` present
 * ONLY for value-taking operators (every op except `empty` / `notEmpty`). A row
 * with an empty field key is dropped; a value-taking row with a blank value is
 * dropped (including `notContains` / `notRegex`, which drop like `contains` /
 * `regex`); valueless `empty` / `notEmpty` rows are kept. The last row wins on a
 * duplicate field key.
 */
export function fromFilterDrafts(
  drafts: FilterDraft[],
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const d of drafts) {
    const field = d.field.trim();
    if (field === '') {
      continue; // unset row → not a filter
    }
    const takesValue = !operatorTakesNoValue(d.op);
    const value = d.value.trim();
    if (takesValue && value === '') {
      continue; // blank value-taking row → never narrows, so drop it
    }
    result[field] = takesValue ? { op: d.op, value } : { op: d.op };
  }
  return result;
}

/**
 * Build the composable field list from the resolved field config: every field
 * present (fixed ⊕ overlay ⊕ calculated), skipping entries explicitly hidden
 * (`visible === false`) and any without a key. Order follows the config's own
 * order (already sorted by the module), so the picker reflects the tenant's
 * configured field set verbatim (R4.5 / R6.1).
 */
export function pickableFields(fieldConfig: FieldConfig | null): FieldConfigField[] {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return [];
  return fields.filter(
    (f): f is FieldConfigField =>
      !!f && typeof f.key === 'string' && f.key !== '' && f.visible !== false,
  );
}

/**
 * Seed the list-column selection for the picker, matching the "missing columns" fix:
 *   1. an explicit saved `listColumns` set seeds verbatim (its own column set);
 *   2. a LEGACY list set (no named list columns, no group columns) seeds the FULL field set so it
 *      renders its full column set rather than near-empty (the "missing columns" fix). An
 *      aggregate set (group columns present) seeds no list columns.
 *   3. a brand-new blank compose (`config === undefined`) seeds NOTHING — the user picks the list
 *      columns they want rather than starting with every field pre-checked. The save validation
 *      still requires ≥1 list column for a list set, so a new set can never save near-empty.
 *
 * The `fieldConfig` arg is retained for the legacy-set fallback.
 */
export function seedListColumns(
  config: PivotConfig | undefined,
  fieldConfig: FieldConfig | null,
): string[] {
  const existing = config?.listColumns;
  if (Array.isArray(existing) && existing.length > 0) {
    return existing.filter((k): k is string => typeof k === 'string' && k !== '');
  }
  // Brand-new blank compose: nothing pre-selected (user's explicit choice).
  if (!config) {
    return [];
  }
  const isAggregate = (config.groupColumns?.length ?? 0) > 0;
  if (isAggregate) {
    return [];
  }
  // Legacy saved/preset list set with no named columns → full set fallback.
  return pickableFields(fieldConfig).map((f) => f.key);
}
