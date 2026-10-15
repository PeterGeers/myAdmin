/**
 * memberPivotViewsHelpers — the pure, stateless helpers extracted from
 * `MemberPivotViews.tsx` (code-quality split 2026-10-15, task 4).
 *
 * These carry ZERO behaviour change: every function here is the verbatim
 * stateless logic the pivot-views panel used inline. Keeping them in a sibling
 * module shrinks the (very large) component file while leaving the public import
 * surface (`MemberPivotViews` default export + the analytics barrel) untouched.
 *
 * @module components/members/analytics/memberPivotViewsHelpers
 */

import type { PivotConfig } from '../../../types/pivot';
import type { AggregateFunction } from '../../../types/pivot';
import type { LocalizedLabel } from '../../../types/members';
import { getAnalyticsSet } from '../../../services/membersApiService';

/**
 * A selectable set in the dropdown — a materialized preset or a saved member
 * model — flattened to the small shape the dropdown + Execute need.
 */
export interface SelectableSet {
  /** Stable, collision-free option value (`model:<id>`). */
  optionValue: string;
  /** Already-resolved display label (the saved model name). */
  label: string;
  /** Which group the option belongs to (saved member models only). */
  source: 'model';
  /** A saved set's id (the backend `set_id` string), loaded on Execute. */
  modelId?: string;
}

export const MODEL_PREFIX = 'model:';

// The preferred list (R11.2) stores TAGGED references, not copies: a saved
// tenant-shared set is `set:<id>`. The dropdown's internal option scheme uses
// `model:<id>` for a saved set; these two helpers bridge the two so the
// preferred list speaks the backend's `set:` vocabulary.
export const SET_PREFIX = 'set:';

/**
 * Convert a dropdown option value (`model:<id>`) into the backend preferred-list
 * tagged reference (`set:<id>`). Returns null when the option value is not a
 * recognizable saved-set reference.
 */
export function optionValueToRef(optionValue: string): string | null {
  if (optionValue.startsWith(MODEL_PREFIX)) {
    return `${SET_PREFIX}${optionValue.slice(MODEL_PREFIX.length)}`;
  }
  return null;
}

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language,
 * mirroring the field picker's `resolveLabel` (prefer active language, then
 * `nl`, then `en`, then the fallback). Kept local so the result-header label map
 * is built from the SAME field config the picker lists (no hardcoded English,
 * findings: "result column headers stay English").
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

/**
 * Parse an aggregate result-column name of the SQL-style form `FUNC(column)`
 * (e.g. `COUNT(*)`, `SUM(age)`) into its function + inner column, or `null` when
 * the name is not an aggregate expression (a plain group/list column key). Used
 * to build a localized aggregate header ("Aantal (Leeftijd)" / "Count (Age)")
 * from the field config + an i18n function label.
 */
export function parseAggregateName(
  name: string,
): { fn: AggregateFunction; inner: string } | null {
  const match = /^([A-Z]+)\((.*)\)$/.exec(name);
  if (!match) {
    return null;
  }
  const fn = match[1] as AggregateFunction;
  return { fn, inner: match[2] };
}

/**
 * Resolve the `PivotConfig` for the chosen set. A saved set's full definition is
 * fetched via the Members API `getAnalyticsSet` (which converts the module's
 * snake_case `definition` into a camelCase `PivotConfig`), so the saved set's own
 * definition filters travel with it (R4.4), never the page's live filter
 * (R4.4a).
 */
export async function resolveConfig(set: SelectableSet): Promise<PivotConfig | undefined> {
  if (typeof set.modelId === 'string') {
    const saved = await getAnalyticsSet(set.modelId);
    return saved.definition;
  }
  return undefined;
}
