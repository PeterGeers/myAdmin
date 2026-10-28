/**
 * Tests for usePivotConfig (pivot builder config state hook).
 *
 * Focuses on the synchronous setter + derived-state branch logic, which is the
 * medium-value gap: validation, config-reset on data-source change, the
 * display-mode/rollup auto-derivation from group count, measure add/remove caps,
 * pivot↔nest clearing, and the column-role exclusion helpers.
 *
 * pivotService is mocked so the mount effects resolve to empty data and do not
 * hit the network; these tests assert on the pure state transitions, not fetch.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { AvailableColumns, PivotDataSource } from '../../types/pivot';
import {
  usePivotConfig,
  MAX_GROUP_COLUMNS,
  MAX_AGGREGATE_MEASURES,
  MAX_NEST_LEVELS,
} from './usePivotConfig';

// ─── Mock pivotService (mount effects) ───────────────────────────────────────

const mockGetRegisteredSources = vi.fn<() => Promise<PivotDataSource[]>>();
const mockGetAvailableColumns = vi.fn<(ds: string) => Promise<AvailableColumns>>();

vi.mock('../../services/pivotService', () => ({
  getRegisteredSources: () => mockGetRegisteredSources(),
  filterSourcesByModule: (sources: PivotDataSource[]) => sources,
  getAvailableColumns: (ds: string) => mockGetAvailableColumns(ds),
}));

const EMPTY_COLS: AvailableColumns = { groupable: [], aggregatable: [] };

beforeEach(() => {
  vi.clearAllMocks();
  mockGetRegisteredSources.mockResolvedValue([]);
  mockGetAvailableColumns.mockResolvedValue(EMPTY_COLS);
});

/** Render the hook and wait for the data-source mount effect to settle. */
async function renderSettled(options = {}) {
  const hook = renderHook(() => usePivotConfig(options));
  await waitFor(() => expect(hook.result.current.dataSourcesLoading).toBe(false));
  return hook;
}

describe('usePivotConfig — validation', () => {
  it('is invalid with no data source and reports missing group/measure', async () => {
    const { result } = await renderSettled();

    expect(result.current.isValid).toBe(false);
    expect(result.current.validation.groupColumns).toBe('minGroupColumn');
    expect(result.current.validation.aggregateMeasures).toBe('minAggregateMeasure');
  });

  it('becomes valid once a data source, a group column and a measure are set', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setDataSource('vw_mutaties'));
    act(() => result.current.setGroupColumns(['region']));
    act(() => result.current.addAggregateMeasure());

    expect(result.current.validation).toEqual({});
    expect(result.current.isValid).toBe(true);
  });

  it('flags a column used in two roles as a role overlap', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setDataSource('vw_mutaties'));
    act(() => result.current.setGroupColumns(['region']));
    act(() => result.current.setColumnPivot('region'));

    expect(result.current.validation.columnRoleOverlap).toBe('region');
    expect(result.current.isValid).toBe(false);
  });
});

describe('usePivotConfig — setters and auto-derivation', () => {
  it('setDataSource resets the rest of the config', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setGroupColumns(['a', 'b']));
    act(() => result.current.addAggregateMeasure());
    act(() => result.current.setDataSource('vw_new'));

    expect(result.current.config.dataSource).toBe('vw_new');
    expect(result.current.config.groupColumns).toEqual([]);
    expect(result.current.config.aggregateMeasures).toEqual([]);
  });

  it('caps group columns at MAX_GROUP_COLUMNS', async () => {
    const { result } = await renderSettled();
    const many = Array.from({ length: MAX_GROUP_COLUMNS + 3 }, (_, i) => `c${i}`);

    act(() => result.current.setGroupColumns(many));

    expect(result.current.config.groupColumns).toHaveLength(MAX_GROUP_COLUMNS);
  });

  it('auto-switches to hierarchical+rollup at 2 group columns and back to flat below 2', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setGroupColumns(['a', 'b']));
    expect(result.current.config.displayMode).toBe('hierarchical');
    expect(result.current.config.includeRollup).toBe(true);

    act(() => result.current.setGroupColumns(['a']));
    expect(result.current.config.displayMode).toBe('flat');
    expect(result.current.config.includeRollup).toBe(false);
  });

  it('addAggregateMeasure stops at MAX_AGGREGATE_MEASURES', async () => {
    const { result } = await renderSettled();

    act(() => {
      for (let i = 0; i < MAX_AGGREGATE_MEASURES + 2; i++) {
        result.current.addAggregateMeasure();
      }
    });

    expect(result.current.config.aggregateMeasures).toHaveLength(MAX_AGGREGATE_MEASURES);
  });

  it('updateAggregateMeasure / removeAggregateMeasure target the right index', async () => {
    const { result } = await renderSettled();

    act(() => result.current.addAggregateMeasure());
    act(() => result.current.addAggregateMeasure());
    act(() => result.current.updateAggregateMeasure(1, { function: 'COUNT', column: 'id' }));

    expect(result.current.config.aggregateMeasures[1]).toEqual({ function: 'COUNT', column: 'id' });

    act(() => result.current.removeAggregateMeasure(0));
    expect(result.current.config.aggregateMeasures).toEqual([{ function: 'COUNT', column: 'id' }]);
  });

  it('clears nest levels when the column pivot is cleared', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setColumnPivot('year'));
    act(() => result.current.setColumnNestLevels(['quarter', 'month']));
    expect(result.current.config.columnNestLevels).toEqual(['quarter', 'month']);

    act(() => result.current.setColumnPivot(null));
    expect(result.current.config.columnPivot).toBeNull();
    expect(result.current.config.columnNestLevels).toEqual([]);
  });

  it('caps nest levels at MAX_NEST_LEVELS', async () => {
    const { result } = await renderSettled();
    const many = Array.from({ length: MAX_NEST_LEVELS + 2 }, (_, i) => `n${i}`);

    act(() => result.current.setColumnPivot('year'));
    act(() => result.current.setColumnNestLevels(many));

    expect(result.current.config.columnNestLevels).toHaveLength(MAX_NEST_LEVELS);
  });

  it('setDisplayMode=hierarchical forces rollup on; flat preserves the current flag', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setDisplayMode('hierarchical'));
    expect(result.current.config.includeRollup).toBe(true);

    act(() => result.current.setIncludeRollup(false));
    act(() => result.current.setDisplayMode('flat'));
    expect(result.current.config.includeRollup).toBe(false);
  });

  it('updateFilter merges a single key while setFilters replaces the map', async () => {
    const { result } = await renderSettled();

    act(() => result.current.updateFilter('region', 'Noord'));
    act(() => result.current.updateFilter('year', '2025'));
    expect(result.current.config.filters).toEqual({ region: 'Noord', year: '2025' });

    act(() => result.current.setFilters({ only: 'x' }));
    expect(result.current.config.filters).toEqual({ only: 'x' });
  });

  it('resetConfig clears everything including the data source', async () => {
    const { result } = await renderSettled();

    act(() => result.current.setDataSource('vw_mutaties'));
    act(() => result.current.setGroupColumns(['region']));
    act(() => result.current.resetConfig());

    expect(result.current.config.dataSource).toBe('');
    expect(result.current.config.groupColumns).toEqual([]);
  });
});

describe('usePivotConfig — column role exclusion helpers', () => {
  const columns: AvailableColumns = {
    groupable: [
      { name: 'region', type: 'varchar', label: 'Region' },
      { name: 'year', type: 'int', label: 'Year' },
      { name: 'month', type: 'int', label: 'Month' },
    ],
    aggregatable: [],
  };

  it('excludes a column from the other roles once it is used in one', async () => {
    mockGetAvailableColumns.mockResolvedValue(columns);
    const { result } = await renderSettled();

    act(() => result.current.setDataSource('vw_mutaties'));
    await waitFor(() => expect(result.current.columns.groupable).toHaveLength(3));

    act(() => result.current.setGroupColumns(['region']));
    act(() => result.current.setColumnPivot('year'));

    // region is a group column → not offered for pivot/nesting
    expect(result.current.availableForPivot.map(c => c.name)).not.toContain('region');
    expect(result.current.availableForNesting.map(c => c.name)).not.toContain('region');
    // year is the pivot → not offered for grouping/nesting
    expect(result.current.availableForGrouping.map(c => c.name)).not.toContain('year');
    expect(result.current.availableForNesting.map(c => c.name)).not.toContain('year');
    // month is still free for every role
    expect(result.current.availableForGrouping.map(c => c.name)).toContain('month');
    expect(result.current.availableForPivot.map(c => c.name)).toContain('month');
    expect(result.current.availableForNesting.map(c => c.name)).toContain('month');
  });
});
