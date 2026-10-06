/**
 * Shared chart components.
 *
 * Barrel for domain-agnostic charts. The generic, reusable ViolinChart (and its
 * `violinStats` helper) is extracted here from `reports/BnbViolinsReport.tsx` so
 * STR/BNB and Member Analytics consume one implementation. Spec:
 * `.kiro/specs/Members/member-analytics` (design C3).
 *
 * Scaffolding (task 0.1). Exports are added by later phases:
 *   - violinStats (task 1.2) ✓
 *   - ViolinChart (task 2.1) ✓
 */
export { violinStats } from './violinStats';
export type { ViolinStats } from './violinStats';

export { default as ViolinChart } from './ViolinChart';
export type { ViolinDatum, ViolinChartProps } from './ViolinChart';
