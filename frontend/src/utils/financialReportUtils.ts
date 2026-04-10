/**
 * Shared utility functions for Balance and P&L report components.
 * Extracted from ActualsReport.tsx for reuse across both report pages.
 */

import { authenticatedPost } from '../services/apiService';
import type { PLRecord } from '../types/financialReports';

/**
 * Format a numeric amount for display based on the selected format.
 * Uses nl-NL locale with € prefix.
 */
export function formatAmount(amount: number, format: string): string {
  const num = Number(amount) || 0;

  switch (format) {
    case '2dec':
      return `€${num.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
    case '0dec':
      return `€${Math.round(num).toLocaleString('nl-NL')}`;
    case 'k':
      return `€${(num / 1000).toFixed(1)}K`;
    case 'm':
      return `€${(num / 1000000).toFixed(1)}M`;
    default:
      return `€${num.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
  }
}

/**
 * Invalidate the backend MutatiesCache, then call the provided fetch function
 * to reload fresh data. Swallows invalidation errors (stale data is acceptable).
 */
export async function invalidateAndFetch(fetchFn: () => Promise<void>): Promise<void> {
  try {
    await authenticatedPost('/api/cache/invalidate', {});
  } catch (err) {
    console.warn('Cache invalidation failed, proceeding with fetch:', err);
  }
  await fetchFn();
}

/**
 * Generate column keys for the report table based on selected years and drill-down level.
 * Returns chronologically sorted keys.
 */
export function generateColumnKeys(
  years: string[],
  drillDownLevel: 'year' | 'quarter' | 'month'
): string[] {
  const sortedYears = [...years].sort((a, b) => parseInt(a) - parseInt(b));

  if (drillDownLevel === 'year') {
    return sortedYears;
  }

  if (drillDownLevel === 'quarter') {
    return sortedYears.flatMap(year =>
      ['Q1', 'Q2', 'Q3', 'Q4'].map(q => `${year}-${q}`)
    );
  }

  // month
  return sortedYears.flatMap(year =>
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
      .map(m => `${year}-${m}`)
  );
}

/**
 * Filter records by VW flag value.
 * VW='N' for balance accounts, VW='Y' for P&L accounts.
 */
export function filterByVW<T extends { VW?: string }>(data: T[], vwFlag: 'N' | 'Y'): T[] {
  return data.filter(record => record.VW === vwFlag);
}

/**
 * Split P&L records into profit (revenue) and loss (cost) sets based on Parent prefix.
 * Revenue accounts start with profitPrefix (e.g. "8"), cost accounts start with lossPrefix (e.g. "4").
 * Records with other Parent prefixes are excluded from both sets.
 */
export function splitChartData(
  data: PLRecord[],
  profitPrefix: string,
  lossPrefix: string
): { profit: PLRecord[]; loss: PLRecord[] } {
  return {
    profit: data.filter(r => r.Parent.startsWith(profitPrefix)),
    loss: data.filter(r => r.Parent.startsWith(lossPrefix)),
  };
}
