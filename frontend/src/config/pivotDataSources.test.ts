/**
 * Tests for the pivot data-source registry (pivotDataSources.ts).
 * Covers the registered sources and the unknown-source filter fallback.
 */

import { describe, it, expect } from 'vitest';
import { PIVOT_DATA_SOURCES, getFilterConfig } from './pivotDataSources';

describe('pivotDataSources', () => {
  it('registers the known sources with stable keys + labels', () => {
    expect(PIVOT_DATA_SOURCES.map((s) => s.key)).toEqual(['vw_mutaties', 'vw_bnb_total']);
    expect(PIVOT_DATA_SOURCES.map((s) => s.label)).toEqual([
      'Financial Transactions',
      'STR Revenue',
    ]);
  });

  it('returns the registered filter config for a known source', () => {
    expect(getFilterConfig('vw_mutaties').filterKeys).toEqual([
      'years',
      'administration',
      'profitLoss',
      'ledger',
    ]);
    expect(getFilterConfig('vw_bnb_total').filterKeys).toEqual(['years', 'channel', 'listing']);
  });

  it('falls back to an empty filter config for an unknown source', () => {
    expect(getFilterConfig('does_not_exist')).toEqual({ filterKeys: [] });
    expect(getFilterConfig('')).toEqual({ filterKeys: [] });
  });
});
