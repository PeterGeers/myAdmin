/**
 * Pivot Data Source Registry
 *
 * Static configuration for known pivot data sources. Each entry describes
 * a data source key, its human-readable label, and which filter components
 * the PivotBuilder should render when that source is selected.
 *
 * Adding a new data source on the frontend = add one entry to this array.
 * No component changes needed.
 *
 * Note: The actual list of *enabled* data sources comes from the backend
 * (GET /api/pivot/sources). This registry provides the filter configuration
 * for sources the frontend knows how to render filters for. Sources returned
 * by the backend that are not in this registry will use an empty filter config.
 *
 * Requirements: 1.1, 2.1
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import type { DataSourceConfig } from '../types/pivot';

/**
 * Known pivot data sources with their filter configurations.
 *
 * filterConfig.filterKeys lists the filter controls the PivotBuilder
 * should render for each source. These map to existing filter components:
 *   - 'years'          → YearFilter
 *   - 'administration' → administration dropdown (GenericFilter)
 *   - 'profitLoss'     → V/W profit-loss selector (GenericFilter)
 *   - 'ledger'         → ledger account selector (GenericFilter)
 *   - 'channel'        → booking channel dropdown (GenericFilter)
 *   - 'listing'        → property listing dropdown (GenericFilter)
 */
export const PIVOT_DATA_SOURCES: DataSourceConfig[] = [
  {
    key: 'vw_mutaties',
    label: 'Financial Transactions',
    filterConfig: {
      filterKeys: ['years', 'administration', 'profitLoss', 'ledger'],
    },
  },
  {
    key: 'vw_bnb_total',
    label: 'STR Revenue',
    filterConfig: {
      filterKeys: ['years', 'channel', 'listing'],
    },
  },
];

/**
 * Look up the filter configuration for a data source.
 * Returns an empty filterKeys array for unknown sources.
 */
export function getFilterConfig(dataSourceKey: string): DataSourceConfig['filterConfig'] {
  const source = PIVOT_DATA_SOURCES.find((s) => s.key === dataSourceKey);
  return source?.filterConfig ?? { filterKeys: [] };
}
