/**
 * Type-aware column value coercion for the Members overview sort (session-columns
 * task 2.1, design C4; R2.3).
 *
 * The flat-key rule (see {@link valueFor} in `fieldValue.ts`): a surfaced column
 * filters/sorts iff its key is a flat top-level property of the row. The on-the-fly
 * flatten (design C4) promotes a chosen field's RESOLVED value to a flat key just
 * before the filter engine sees it. The filter engine stringifies (case-insensitive
 * substring), but the SORT compares the raw flat value — so a `number` field must be
 * flattened as a real number and a `date` field as a chronologically-sortable form,
 * else the overview would fall back to a lexical string sort ("10" < "9", "2020-01"
 * ordered by text) which R2.3 forbids.
 *
 * `coerceByType` is the single pure helper that turns a field's resolved value into
 * that sort-correct form, honoring the field `type`:
 *
 * - `number` → `Number(value)`; a value that is not a finite number (NaN, blank,
 *   non-numeric string) falls back to the ORIGINAL value so nothing is lost and the
 *   sort degrades gracefully to the string form rather than becoming `NaN`.
 * - `date`   → a sortable ISO string (via `Date`); an unparseable/blank date falls
 *   back to the original value (same graceful degradation).
 * - anything else → the `String`-safe value.
 *
 * It is READ-only, side-effect free, and never throws — mirroring the
 * never-crash-on-odd-values contract of `renderFieldValue`.
 */

import type { FieldConfigField } from '../../types/members';

/**
 * Coerce a field's resolved value into a sort-correct form keyed off the field
 * `type` (design C4, R2.3). Pure; returns a value safe to compare in
 * `useTableSort` without a lexical-vs-numeric/chronological mismatch.
 *
 * Fallback rule: whenever a typed coercion cannot produce a meaningful value
 * (NaN for `number`, unparseable for `date`), the ORIGINAL value is returned
 * unchanged — never `NaN` or `"Invalid Date"` — so a malformed cell sorts as its
 * raw form instead of corrupting the ordering.
 *
 * - `null`/`undefined` pass through untouched (an absent cell stays absent — the
 *   sort treats it like today's empty value).
 */
export function coerceByType(field: FieldConfigField, value: unknown): unknown {
  if (value === null || value === undefined) {
    return value;
  }

  switch (field.type) {
    case 'number':
      return coerceNumber(value);
    case 'date':
      return coerceDate(value);
    default:
      return String(value);
  }
}

/**
 * `number` → a finite JS number; falls back to the original value when the input
 * is blank, NaN, or otherwise not a finite number (so the sort degrades to the
 * raw form rather than comparing against `NaN`).
 */
function coerceNumber(value: unknown): unknown {
  // An empty string coerces to 0 via Number(''), which would misorder a blank
  // cell as zero — treat blank as "no numeric value" and keep the original.
  if (typeof value === 'string' && value.trim() === '') {
    return value;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : value;
}

/**
 * `date` → a chronologically-sortable ISO string; falls back to the original
 * value when the input is blank or cannot be parsed to a valid date.
 */
function coerceDate(value: unknown): unknown {
  if (typeof value === 'string' && value.trim() === '') {
    return value;
  }
  const date = value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString();
}

/**
 * The flat top-level keys that `flattenMember`
 * (`frontend/src/services/membersApiService.ts`) ALREADY promotes onto every
 * member row — the convenience aliases the default table columns read.
 *
 * These keys are already flat `row[key]` properties, mapped by `flattenMember`
 * to the real nested shape, so they are inherently filterable/sortable without
 * any on-the-fly promotion. The column chooser's on-the-fly flatten (design C4)
 * MUST skip them: re-promoting a chosen field whose key is one of these would
 * clobber the carefully-mapped alias (R3.4 — never overwrite an existing flat
 * alias; only non-alias keys are promoted).
 *
 * Kept in lockstep with the alias set `flattenMember` returns:
 * `member_number, name, email, status, membership_type, region, membership_id`.
 */
export const FLAT_ALIASES: ReadonlySet<string> = new Set([
  'member_number',
  'name',
  'email',
  'status',
  'membership_type',
  'region',
  'membership_id',
]);

/**
 * Is `key` one of the flat aliases `flattenMember` already promotes
 * ({@link FLAT_ALIASES})? The guard the on-the-fly flatten uses so an existing
 * alias is never overwritten (R3.4).
 */
export function isFlatAlias(key: string): boolean {
  return FLAT_ALIASES.has(key);
}

/**
 * Should a chosen field `key` be promoted by the on-the-fly flatten (design
 * C4)? True for every key EXCEPT the flat aliases `flattenMember` already
 * carries — those are left untouched so the chooser never clobbers them (R3.4).
 *
 * The exclusion helper the `enrichedRows` memo uses to pick which chosen keys
 * to promote, e.g. `chosenColumns.filter((f) => shouldFlatten(f.key))`.
 */
export function shouldFlatten(key: string): boolean {
  return !isFlatAlias(key);
}
