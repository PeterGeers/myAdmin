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
  PivotConfig,
} from '../../../types/pivot';

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

/**
 * The reserved definition-filter keys the jubilee / new-members selectors own
 * (mirrors `analyticsConfig`'s `JUBILEE_YEAR_FILTER_KEY` /
 * `JOINED_AFTER_FILTER_KEY`). The picker's generic Filters section never shows
 * or clobbers these — they are year-aware filters driven by the Pivot Views
 * selector UI, so they are carried through untouched on the composed config.
 * Hardcoded here (rather than imported) to keep the picker's definition filters
 * independent of the selector plumbing.
 */
export const RESERVED_FILTER_KEYS: readonly string[] = ['years_member', 'joined_after_year'];

/** A single composable definition-filter row in local state (stable id for React keys). */
export interface FilterDraft {
  id: string;
  /** Field key the filter matches on, or `''` (unset row). */
  field: string;
  /** The value the field must equal (string equality, applied at execute time). */
  value: string;
}

let filterIdSeq = 0;
export function nextFilterId(): string {
  filterIdSeq += 1;
  return `filter-${filterIdSeq}`;
}

/**
 * Seed the editable filter rows from a config's `filters` map, SKIPPING the
 * reserved year keys (they are not generic equality filters). Each remaining
 * entry becomes an editable row so a saved set's definition filters round-trip
 * through the editor (R4.4). A value is stringified for the text input.
 */
export function toFilterDrafts(
  filters: Record<string, unknown> | undefined,
): FilterDraft[] {
  if (!filters) return [];
  const drafts: FilterDraft[] = [];
  for (const [field, raw] of Object.entries(filters)) {
    if (RESERVED_FILTER_KEYS.includes(field)) {
      continue;
    }
    if (raw === null || raw === undefined) {
      continue;
    }
    drafts.push({ id: nextFilterId(), field, value: String(raw) });
  }
  return drafts;
}

/**
 * Compose the editable filter rows back into a `{ [fieldKey]: value }` map,
 * MERGED onto the set's existing reserved filters (so a jubilee/joined-after
 * year is preserved). Blank rows (no field, or no value) are dropped; the last
 * row wins on a duplicate field key.
 */
export function fromFilterDrafts(
  drafts: FilterDraft[],
  base: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  // Carry the reserved year filters from the base config untouched.
  if (base) {
    for (const key of RESERVED_FILTER_KEYS) {
      if (key in base && base[key] !== undefined && base[key] !== null) {
        result[key] = base[key];
      }
    }
  }
  for (const d of drafts) {
    const field = d.field.trim();
    const value = d.value.trim();
    if (field === '' || value === '') {
      continue; // blank row → not a filter
    }
    result[field] = value;
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
