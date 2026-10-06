/**
 * Member Analytics — pure numeric-aggregation helpers (C2).
 *
 * The Overview summary (R2) and the violin distributions (R3) are computed over
 * the Analytics page's own filtered dataset. The calculated fields they read —
 * `age`, `years_member` — are typed `string` by the Members module (an int is
 * computed server-side then stringified), so analytics MUST parse them to a
 * number before averaging. These helpers are the single parse + aggregate path.
 *
 * Rules the spec pins down:
 *   - `toNumber` accepts a real `number` or a numeric string and returns a finite
 *     `number`; anything absent, non-numeric, or non-finite returns `null`
 *     (never coerced to 0) — R2.3 / design C2 / OQ3-D4.
 *   - `mean` averages over *present* values only — rows whose input is absent or
 *     unparseable are excluded from the average, never counted as zero (R2.3).
 *   - `countExcluded` reports how many raw inputs were absent/invalid, so the
 *     Overview can surface an excluded-count where it aids interpretation (R2.3).
 *
 * Pure + unit-tested. No React, no I/O. Spec:
 * `.kiro/specs/Members/member-analytics` (design C2; R2.1, R2.3, R3.5).
 */

/**
 * Parse an arbitrary field value to a finite number, or `null` when it is
 * absent, non-numeric, or non-finite.
 *
 * Accepts:
 *   - a finite `number` (returned as-is; `NaN`/`±Infinity` → `null`);
 *   - a numeric string, with surrounding whitespace tolerated (`" 42 "` → 42,
 *     `"3.5"` → 3.5, `"-7"` → -7).
 *
 * Rejects (→ `null`): `null`, `undefined`, empty / whitespace-only string,
 * non-numeric string (`"abc"`, `"12abc"`), booleans, objects, arrays, `NaN`,
 * `±Infinity`. Rows that resolve to `null` are *excluded* from aggregation
 * rather than treated as 0 (R2.3).
 */
export function toNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed === '') {
      return null;
    }
    // Number() tolerates leading/trailing space but, unlike parseFloat, rejects
    // trailing garbage ("12abc" → NaN) — exactly the strict parse we want.
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * Mean of a list of numbers, computed over present values only.
 *
 * Each entry is passed through {@link toNumber}, so a `number[]` is averaged
 * directly while a raw `unknown[]` (e.g. the stringified calculated-field values
 * straight off the rows) is parsed and filtered in one step. Entries that do not
 * parse to a finite number are excluded from both the sum and the divisor
 * (R2.3 — never counted as zero).
 *
 * Returns `null` when no value is present/valid (an empty or fully-excluded
 * input), so the caller can omit the figure rather than render `NaN` or a
 * misleading 0.
 */
export function mean(values: readonly unknown[]): number | null {
  let sum = 0;
  let count = 0;
  for (const value of values) {
    const n = toNumber(value);
    if (n !== null) {
      sum += n;
      count += 1;
    }
  }
  return count === 0 ? null : sum / count;
}

/**
 * Count how many of the given raw inputs are absent or invalid — i.e. the number
 * of entries {@link toNumber} rejects. This is the excluded-count the Overview
 * may surface alongside an average so the figure is interpretable (R2.3): e.g.
 * "avg age 47 (3 of 120 excluded — no birth date)".
 *
 * Operates on the same raw `unknown[]` the aggregation reads, so the excluded
 * count and the averaged count always agree (present + excluded === total).
 */
export function countExcluded(values: readonly unknown[]): number {
  let excluded = 0;
  for (const value of values) {
    if (toNumber(value) === null) {
      excluded += 1;
    }
  }
  return excluded;
}
