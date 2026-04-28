/**
 * Unit tests for pivotService.ts
 *
 * Tests all API client functions, camelCase ↔ snake_case conversion helpers,
 * filterSourcesByModule, and error handling for failed requests.
 *
 * Requirements: 3.1, 4.1, 5.1
 * Reference: .kiro/specs/dynamic-pivot-views/tasks.md §11.7
 */

import { vi } from 'vitest';
import {
  executePivot,
  getAvailableColumns,
  getRegisteredSources,
  listPivotModels,
  loadPivotModel,
  savePivotModel,
  updatePivotModel,
  deletePivotModel,
  exportUnderlying,
  filterSourcesByModule,
  toBackendConfig,
  fromBackendConfig,
} from '../pivotService';
import type { PivotConfig, PivotDataSource } from '../../types/pivot';

// ---------------------------------------------------------------------------
// Mock apiService
// ---------------------------------------------------------------------------

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock('../apiService', () => ({
  authenticatedGet: (...args: any[]) => mockGet(...args),
  authenticatedPost: (...args: any[]) => mockPost(...args),
  authenticatedPut: (...args: any[]) => mockPut(...args),
  authenticatedDelete: (...args: any[]) => mockDelete(...args),
  buildEndpoint: (endpoint: string) => endpoint,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a mock Response with ok=true and the given JSON body. */
const okJson = (data: any): Response =>
  ({ ok: true, status: 200, json: async () => data } as unknown as Response);

/** Build a mock Response with ok=false and an error body. */
const errJson = (status: number, error: string): Response =>
  ({ ok: false, status, json: async () => ({ error }) } as unknown as Response);

/** Build a mock Response where .json() itself rejects (network-level issue). */
const brokenJson = (status: number): Response =>
  ({
    ok: false,
    status,
    json: async () => {
      throw new Error('body parse failed');
    },
  } as unknown as Response);

/** A minimal valid PivotConfig for reuse across tests. */
const SAMPLE_CONFIG: PivotConfig = {
  dataSource: 'vw_mutaties',
  groupColumns: ['Aangifte', 'jaar'],
  aggregateMeasures: [
    { function: 'SUM', column: 'Amount' },
    { function: 'COUNT', column: '*' },
  ],
  filters: { years: [2024, 2025] },
  columnPivot: null,
  columnNestLevels: [],
  displayMode: 'hierarchical',
  includeRollup: true,
};

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => vi.clearAllMocks());

// ===========================================================================
// toBackendConfig / fromBackendConfig
// ===========================================================================

describe('toBackendConfig', () => {
  it('converts camelCase config to snake_case', () => {
    const result = toBackendConfig(SAMPLE_CONFIG);

    expect(result).toEqual({
      data_source: 'vw_mutaties',
      group_columns: ['Aangifte', 'jaar'],
      aggregate_measures: [
        { function: 'SUM', column: 'Amount' },
        { function: 'COUNT', column: '*' },
      ],
      filters: { years: [2024, 2025] },
      column_pivot: null,
      column_nest_levels: [],
      include_rollup: true,
      display_mode: 'hierarchical',
    });
  });

  it('defaults includeRollup to false when undefined', () => {
    const config: PivotConfig = { ...SAMPLE_CONFIG, includeRollup: undefined };
    const result = toBackendConfig(config);
    expect(result.include_rollup).toBe(false);
  });

  it('defaults displayMode to flat when undefined', () => {
    const config = { ...SAMPLE_CONFIG, displayMode: undefined } as any;
    const result = toBackendConfig(config);
    expect(result.display_mode).toBe('flat');
  });

  it('preserves column pivot and nest levels', () => {
    const config: PivotConfig = {
      ...SAMPLE_CONFIG,
      columnPivot: 'jaar',
      columnNestLevels: ['kwartaal', 'maand'],
    };
    const result = toBackendConfig(config);
    expect(result.column_pivot).toBe('jaar');
    expect(result.column_nest_levels).toEqual(['kwartaal', 'maand']);
  });
});

describe('fromBackendConfig', () => {
  it('converts snake_case definition to camelCase PivotConfig', () => {
    const backend = {
      data_source: 'vw_bnb_total',
      group_columns: ['channel', 'year'],
      aggregate_measures: [{ function: 'SUM', column: 'amountGross' }],
      filters: {},
      column_pivot: 'year',
      column_nest_levels: ['q'],
      display_mode: 'flat',
      include_rollup: false,
    };

    const result = fromBackendConfig(backend);

    expect(result).toEqual({
      dataSource: 'vw_bnb_total',
      groupColumns: ['channel', 'year'],
      aggregateMeasures: [{ function: 'SUM', column: 'amountGross' }],
      filters: {},
      columnPivot: 'year',
      columnNestLevels: ['q'],
      displayMode: 'flat',
      includeRollup: false,
    });
  });

  it('handles already-camelCase keys (fallback)', () => {
    const mixed = {
      dataSource: 'vw_mutaties',
      groupColumns: ['Aangifte'],
      aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'hierarchical',
      includeRollup: true,
    };

    const result = fromBackendConfig(mixed);
    expect(result.dataSource).toBe('vw_mutaties');
    expect(result.groupColumns).toEqual(['Aangifte']);
    expect(result.displayMode).toBe('hierarchical');
  });

  it('defaults missing fields to safe values', () => {
    const result = fromBackendConfig({});

    expect(result.dataSource).toBe('');
    expect(result.groupColumns).toEqual([]);
    expect(result.aggregateMeasures).toEqual([]);
    expect(result.filters).toEqual({});
    expect(result.columnPivot).toBeNull();
    expect(result.columnNestLevels).toEqual([]);
    expect(result.displayMode).toBe('flat');
    expect(result.includeRollup).toBe(false);
  });

  it('round-trips through toBackendConfig → fromBackendConfig', () => {
    const roundTripped = fromBackendConfig(toBackendConfig(SAMPLE_CONFIG));

    expect(roundTripped.dataSource).toBe(SAMPLE_CONFIG.dataSource);
    expect(roundTripped.groupColumns).toEqual(SAMPLE_CONFIG.groupColumns);
    expect(roundTripped.aggregateMeasures).toEqual(SAMPLE_CONFIG.aggregateMeasures);
    expect(roundTripped.filters).toEqual(SAMPLE_CONFIG.filters);
    expect(roundTripped.columnPivot).toBe(SAMPLE_CONFIG.columnPivot);
    expect(roundTripped.columnNestLevels).toEqual(SAMPLE_CONFIG.columnNestLevels);
    expect(roundTripped.displayMode).toBe(SAMPLE_CONFIG.displayMode);
    expect(roundTripped.includeRollup).toBe(SAMPLE_CONFIG.includeRollup);
  });
});

// ===========================================================================
// filterSourcesByModule
// ===========================================================================

const SOURCES: PivotDataSource[] = [
  { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
  { name: 'vw_bnb_total', label: 'STR Revenue', module: 'STR' },
  { name: 'vw_zzp_invoices', label: 'ZZP Invoices', module: 'ZZP' },
  { name: 'vw_generic', label: 'Generic View', module: null },
];

describe('filterSourcesByModule', () => {
  it('returns only FIN sources when moduleFilter is FIN', () => {
    const result = filterSourcesByModule(SOURCES, 'FIN');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_mutaties');
  });

  it('returns only STR sources when moduleFilter is STR', () => {
    const result = filterSourcesByModule(SOURCES, 'STR');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_bnb_total');
  });

  it('returns only ZZP sources when moduleFilter is ZZP', () => {
    const result = filterSourcesByModule(SOURCES, 'ZZP');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_zzp_invoices');
  });

  it('returns ALL sources when moduleFilter is undefined', () => {
    const result = filterSourcesByModule(SOURCES);
    expect(result).toHaveLength(4);
  });

  it('returns ALL sources when moduleFilter is null', () => {
    const result = filterSourcesByModule(SOURCES, null);
    expect(result).toHaveLength(4);
  });

  it('returns empty array when no sources match the module', () => {
    const sources: PivotDataSource[] = [
      { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
    ];
    const result = filterSourcesByModule(sources, 'STR');
    expect(result).toHaveLength(0);
  });

  it('excludes untagged sources when a module filter is active', () => {
    const result = filterSourcesByModule(SOURCES, 'FIN');
    const names = result.map((s) => s.name);
    expect(names).not.toContain('vw_generic');
  });
});

// ===========================================================================
// getRegisteredSources
// ===========================================================================

describe('getRegisteredSources', () => {
  it('calls GET /api/pivot/sources and returns data array', async () => {
    const data = [
      { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
    ];
    mockGet.mockResolvedValue(okJson({ success: true, data }));

    const result = await getRegisteredSources();

    expect(mockGet).toHaveBeenCalledWith('/api/pivot/sources');
    expect(result).toEqual(data);
  });

  it('throws on non-ok response', async () => {
    mockGet.mockResolvedValue(errJson(500, 'Internal server error'));
    await expect(getRegisteredSources()).rejects.toThrow('Internal server error');
  });
});

// ===========================================================================
// getAvailableColumns
// ===========================================================================

describe('getAvailableColumns', () => {
  it('calls GET /api/pivot/columns/<source> and returns columns', async () => {
    const groupable = [{ name: 'Aangifte', type: 'varchar', label: 'Aangifte' }];
    const aggregatable = [{ name: 'Amount', type: 'decimal', label: 'Amount' }];
    mockGet.mockResolvedValue(okJson({ success: true, groupable, aggregatable }));

    const result = await getAvailableColumns('vw_mutaties');

    expect(mockGet).toHaveBeenCalledWith('/api/pivot/columns/vw_mutaties');
    expect(result.groupable).toEqual(groupable);
    expect(result.aggregatable).toEqual(aggregatable);
  });

  it('throws on non-ok response', async () => {
    mockGet.mockResolvedValue(errJson(404, 'Data source not found'));
    await expect(getAvailableColumns('unknown')).rejects.toThrow('Data source not found');
  });
});

// ===========================================================================
// executePivot
// ===========================================================================

describe('executePivot', () => {
  it('calls POST /api/pivot/execute with snake_case body', async () => {
    const responseData = {
      success: true,
      data: [{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 }],
      columns: [],
      row_count: 1,
    };
    mockPost.mockResolvedValue(okJson(responseData));

    const result = await executePivot(SAMPLE_CONFIG);

    expect(mockPost).toHaveBeenCalledWith(
      '/api/pivot/execute',
      expect.objectContaining({
        data_source: 'vw_mutaties',
        group_columns: ['Aangifte', 'jaar'],
        include_rollup: true,
      }),
    );
    expect(result.success).toBe(true);
    expect(result.data).toHaveLength(1);
    expect(result.row_count).toBe(1);
  });

  it('throws on server error', async () => {
    mockPost.mockResolvedValue(errJson(400, 'At least one group column is required'));
    await expect(executePivot(SAMPLE_CONFIG)).rejects.toThrow(
      'At least one group column is required',
    );
  });
});

// ===========================================================================
// exportUnderlying
// ===========================================================================

describe('exportUnderlying', () => {
  it('calls POST /api/pivot/export with snake_case body', async () => {
    const responseData = {
      success: true,
      data: [{ Aangifte: 'BTW', Amount: 100 }],
      row_count: 1,
    };
    mockPost.mockResolvedValue(okJson(responseData));

    const result = await exportUnderlying(SAMPLE_CONFIG);

    expect(mockPost).toHaveBeenCalledWith(
      '/api/pivot/export',
      expect.objectContaining({ data_source: 'vw_mutaties' }),
    );
    expect(result.success).toBe(true);
    expect(result.data).toHaveLength(1);
  });

  it('throws on server error', async () => {
    mockPost.mockResolvedValue(errJson(403, 'Insufficient permissions'));
    await expect(exportUnderlying(SAMPLE_CONFIG)).rejects.toThrow('Insufficient permissions');
  });
});

// ===========================================================================
// listPivotModels
// ===========================================================================

describe('listPivotModels', () => {
  it('calls GET /api/pivot/models and returns data array', async () => {
    const models = [
      { id: 1, name: 'BTW per year', data_source: 'vw_mutaties', created_by: 'user@test.com', created_at: '2025-01-01' },
      { id: 2, name: 'Revenue by channel', data_source: 'vw_bnb_total', created_by: 'user@test.com', created_at: '2025-02-01' },
    ];
    mockGet.mockResolvedValue(okJson({ success: true, data: models }));

    const result = await listPivotModels();

    expect(mockGet).toHaveBeenCalledWith('/api/pivot/models');
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('BTW per year');
  });

  it('throws on non-ok response', async () => {
    mockGet.mockResolvedValue(errJson(401, 'Missing Authorization header'));
    await expect(listPivotModels()).rejects.toThrow('Missing Authorization header');
  });
});

// ===========================================================================
// loadPivotModel
// ===========================================================================

describe('loadPivotModel', () => {
  it('calls GET /api/pivot/models/<id> and converts definition to camelCase', async () => {
    const raw = {
      id: 1,
      name: 'BTW per year',
      data_source: 'vw_mutaties',
      definition: {
        data_source: 'vw_mutaties',
        group_columns: ['Aangifte', 'jaar'],
        aggregate_measures: [{ function: 'SUM', column: 'Amount' }],
        filters: {},
        column_pivot: null,
        column_nest_levels: [],
        display_mode: 'hierarchical',
        include_rollup: true,
      },
      created_by: 'user@test.com',
      created_at: '2025-01-01',
      updated_at: '2025-01-02',
    };
    mockGet.mockResolvedValue(okJson(raw));

    const result = await loadPivotModel(1);

    expect(mockGet).toHaveBeenCalledWith('/api/pivot/models/1');
    expect(result.id).toBe(1);
    // Definition should be converted to camelCase
    expect(result.definition.dataSource).toBe('vw_mutaties');
    expect(result.definition.groupColumns).toEqual(['Aangifte', 'jaar']);
    expect(result.definition.displayMode).toBe('hierarchical');
    expect(result.definition.includeRollup).toBe(true);
  });

  it('throws on model not found', async () => {
    mockGet.mockResolvedValue(errJson(404, 'Pivot model not found'));
    await expect(loadPivotModel(999)).rejects.toThrow('Pivot model not found');
  });
});

// ===========================================================================
// savePivotModel
// ===========================================================================

describe('savePivotModel', () => {
  it('calls POST /api/pivot/models with name and snake_case definition', async () => {
    mockPost.mockResolvedValue(okJson({ success: true, id: 5 }));

    const result = await savePivotModel('My Model', SAMPLE_CONFIG);

    expect(mockPost).toHaveBeenCalledWith('/api/pivot/models', {
      name: 'My Model',
      definition: expect.objectContaining({
        data_source: 'vw_mutaties',
        group_columns: ['Aangifte', 'jaar'],
      }),
    });
    expect(result.success).toBe(true);
    expect(result.id).toBe(5);
  });

  it('throws on duplicate name', async () => {
    mockPost.mockResolvedValue(errJson(409, "A model with name 'My Model' already exists"));
    await expect(savePivotModel('My Model', SAMPLE_CONFIG)).rejects.toThrow(
      "A model with name 'My Model' already exists",
    );
  });
});

// ===========================================================================
// updatePivotModel
// ===========================================================================

describe('updatePivotModel', () => {
  it('calls PUT /api/pivot/models/<id> with snake_case definition', async () => {
    mockPut.mockResolvedValue(okJson({ success: true }));

    await updatePivotModel(3, SAMPLE_CONFIG);

    expect(mockPut).toHaveBeenCalledWith('/api/pivot/models/3', {
      definition: expect.objectContaining({
        data_source: 'vw_mutaties',
        group_columns: ['Aangifte', 'jaar'],
      }),
    });
  });

  it('throws on model not found', async () => {
    mockPut.mockResolvedValue(errJson(404, 'Pivot model not found'));
    await expect(updatePivotModel(999, SAMPLE_CONFIG)).rejects.toThrow('Pivot model not found');
  });
});

// ===========================================================================
// deletePivotModel
// ===========================================================================

describe('deletePivotModel', () => {
  it('calls DELETE /api/pivot/models/<id>', async () => {
    mockDelete.mockResolvedValue(okJson({ success: true }));

    await deletePivotModel(7);

    expect(mockDelete).toHaveBeenCalledWith('/api/pivot/models/7');
  });

  it('throws on model not found', async () => {
    mockDelete.mockResolvedValue(errJson(404, 'Pivot model not found'));
    await expect(deletePivotModel(999)).rejects.toThrow('Pivot model not found');
  });
});

// ===========================================================================
// Error handling — generic scenarios
// ===========================================================================

describe('error handling', () => {
  it('uses status code in error message when body has no error field', async () => {
    const res = {
      ok: false,
      status: 500,
      json: async () => ({}),
    } as unknown as Response;
    mockGet.mockResolvedValue(res);

    await expect(getRegisteredSources()).rejects.toThrow('Request failed with status 500');
  });

  it('falls back to status message when json parsing fails', async () => {
    mockGet.mockResolvedValue(brokenJson(502));

    await expect(listPivotModels()).rejects.toThrow('Request failed with status 502');
  });

  it('propagates network errors from authenticatedGet', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));
    await expect(getAvailableColumns('vw_mutaties')).rejects.toThrow('Network error');
  });

  it('propagates network errors from authenticatedPost', async () => {
    mockPost.mockRejectedValue(new Error('Failed to fetch'));
    await expect(executePivot(SAMPLE_CONFIG)).rejects.toThrow('Failed to fetch');
  });

  it('propagates network errors from authenticatedPut', async () => {
    mockPut.mockRejectedValue(new Error('Connection refused'));
    await expect(updatePivotModel(1, SAMPLE_CONFIG)).rejects.toThrow('Connection refused');
  });

  it('propagates network errors from authenticatedDelete', async () => {
    mockDelete.mockRejectedValue(new Error('Timeout'));
    await expect(deletePivotModel(1)).rejects.toThrow('Timeout');
  });
});
