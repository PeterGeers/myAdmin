/**
 * violinStats — shared quartile-summary helper for violin distributions.
 *
 * The quartile math is lifted VERBATIM from the inline statistics computation in
 * `reports/BnbViolinsReport.tsx` (the per-group `statsData` block), so STR/BNB and
 * Member Analytics compute identical summaries from one implementation.
 * Spec: `.kiro/specs/Members/member-analytics` (design C3, R3.4). Task 1.2.
 *
 * Identical semantics to the BNB original:
 *   - the input is sorted ascending IN PLACE (`values.sort((a, b) => a - b)`);
 *   - min/max are the first/last sorted elements;
 *   - median is the two-middle average for even length, the middle element otherwise;
 *   - q1/q3 use positional indexing `Math.floor(len * 0.25)` / `Math.floor(len * 0.75)`
 *     (NOT linear interpolation);
 *   - mean is the arithmetic average;
 *   - range is max - min.
 *
 * Note: like the BNB original, this mutates the passed array by sorting it. Callers
 * that need to preserve order should pass a copy.
 */
export interface ViolinStats {
  count: number;
  min: number;
  q1: number;
  median: number;
  mean: number;
  q3: number;
  max: number;
  range: number;
}

export function violinStats(values: number[]): ViolinStats {
  const sorted = values.sort((a: number, b: number) => a - b);
  const len = sorted.length;

  const min = sorted[0];
  const max = sorted[len - 1];
  const median = len % 2 === 0
    ? (sorted[len / 2 - 1] + sorted[len / 2]) / 2
    : sorted[Math.floor(len / 2)];
  const q1 = sorted[Math.floor(len * 0.25)];
  const q3 = sorted[Math.floor(len * 0.75)];
  const mean = sorted.reduce((sum: number, val: number) => sum + val, 0) / len;

  return {
    count: len,
    min,
    q1,
    median,
    mean,
    q3,
    max,
    range: max - min,
  };
}
