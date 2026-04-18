/**
 * Unit tests for useTableConfig hook
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §5
 * Requirements: 6.8, 6.9
 */

import { renderHook, waitFor } from '@testing-library/react';
import { useTableConfig, DEFAULTS, TableEntity } from '../useTableConfig';
import * as parameterService from '../../services/parameterService';

// Mock the parameter service
jest.mock('../../services/parameterService');
const mockGetParameters = parameterService.getParameters as jest.MockedFunction<
  typeof parameterService.getParameters
>;

// Suppress console.error in tests that trigger error paths
const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

afterAll(() => {
  consoleSpy.mockRestore();
});

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Helper: build a mock ParametersResponse
// ---------------------------------------------------------------------------

function buildResponse(params: Array<{ key: string; value: any }>) {
  return {
    success: true,
    tenant: 'TestTenant',
    parameters: {
      'ui.tables': params.map((p, i) => ({
        id: i + 1,
        namespace: 'ui.tables',
        key: p.key,
        value: typeof p.value === 'string' ? p.value : JSON.stringify(p.value),
        value_type: 'json' as const,
        scope_origin: 'system' as const,
        is_secret: false,
      })),
    },
  };
}

// ---------------------------------------------------------------------------
// Test: returns correct defaults for each entity
// ---------------------------------------------------------------------------

describe('useTableConfig — defaults', () => {
  it.each<TableEntity>(['chart_of_accounts', 'parameters', 'banking_mutaties'])(
    'returns correct defaults for %s when API returns no matching params',
    async (entity) => {
      mockGetParameters.mockResolvedValue({
        success: true,
        tenant: 'TestTenant',
        parameters: { 'ui.tables': [] },
      });

      const { result } = renderHook(() => useTableConfig(entity));

      // Initially returns defaults while loading
      expect(result.current.columns).toEqual(DEFAULTS[entity].columns);
      expect(result.current.filterableColumns).toEqual(DEFAULTS[entity].filterableColumns);
      expect(result.current.defaultSort).toEqual(DEFAULTS[entity].defaultSort);
      expect(result.current.pageSize).toEqual(DEFAULTS[entity].pageSize);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // After loading, still defaults (no params found)
      expect(result.current.columns).toEqual(DEFAULTS[entity].columns);
      expect(result.current.filterableColumns).toEqual(DEFAULTS[entity].filterableColumns);
      expect(result.current.defaultSort).toEqual(DEFAULTS[entity].defaultSort);
      expect(result.current.pageSize).toEqual(DEFAULTS[entity].pageSize);
      expect(result.current.error).toBeNull();
    },
  );
});

// ---------------------------------------------------------------------------
// Test: merges API response with defaults
// ---------------------------------------------------------------------------

describe('useTableConfig — API merge', () => {
  it('uses API values when all parameters are present', async () => {
    const customColumns = ['col1', 'col2', 'col3'];
    const customFilterable = ['col1', 'col3'];
    const customSort = { field: 'col2', direction: 'desc' };
    const customPageSize = 50;

    mockGetParameters.mockResolvedValue(
      buildResponse([
        { key: 'chart_of_accounts.columns', value: customColumns },
        { key: 'chart_of_accounts.filterable_columns', value: customFilterable },
        { key: 'chart_of_accounts.default_sort', value: customSort },
        { key: 'chart_of_accounts.page_size', value: customPageSize },
      ]),
    );

    const { result } = renderHook(() => useTableConfig('chart_of_accounts'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.columns).toEqual(customColumns);
    expect(result.current.filterableColumns).toEqual(customFilterable);
    expect(result.current.defaultSort).toEqual(customSort);
    expect(result.current.pageSize).toBe(customPageSize);
    expect(result.current.error).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Test: handles API errors gracefully (returns defaults)
// ---------------------------------------------------------------------------

describe('useTableConfig — error handling', () => {
  it('returns defaults when API throws an error', async () => {
    mockGetParameters.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useTableConfig('parameters'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.columns).toEqual(DEFAULTS.parameters.columns);
    expect(result.current.filterableColumns).toEqual(DEFAULTS.parameters.filterableColumns);
    expect(result.current.defaultSort).toEqual(DEFAULTS.parameters.defaultSort);
    expect(result.current.pageSize).toEqual(DEFAULTS.parameters.pageSize);
    expect(result.current.error).toBe('Failed to load table configuration');
  });

  it('returns defaults when API returns success=false', async () => {
    mockGetParameters.mockResolvedValue({
      success: false,
      tenant: 'TestTenant',
      parameters: {},
    });

    const { result } = renderHook(() => useTableConfig('banking_mutaties'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.columns).toEqual(DEFAULTS.banking_mutaties.columns);
    expect(result.current.error).toBe('Failed to load table configuration');
  });
});

// ---------------------------------------------------------------------------
// Test: loading state transitions correctly
// ---------------------------------------------------------------------------

describe('useTableConfig — loading state', () => {
  it('starts with loading=true and transitions to loading=false', async () => {
    let resolvePromise: (value: any) => void;
    const promise = new Promise<any>((resolve) => {
      resolvePromise = resolve;
    });
    mockGetParameters.mockReturnValue(promise);

    const { result } = renderHook(() => useTableConfig('chart_of_accounts'));

    // Initially loading
    expect(result.current.loading).toBe(true);

    // Resolve the API call
    resolvePromise!({
      success: true,
      tenant: 'TestTenant',
      parameters: { 'ui.tables': [] },
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it('returns defaults while loading', () => {
    // Never-resolving promise to keep loading state
    mockGetParameters.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useTableConfig('parameters'));

    expect(result.current.loading).toBe(true);
    expect(result.current.columns).toEqual(DEFAULTS.parameters.columns);
    expect(result.current.filterableColumns).toEqual(DEFAULTS.parameters.filterableColumns);
    expect(result.current.defaultSort).toEqual(DEFAULTS.parameters.defaultSort);
    expect(result.current.pageSize).toEqual(DEFAULTS.parameters.pageSize);
  });
});

// ---------------------------------------------------------------------------
// Test: partial parameter overrides merge correctly
// ---------------------------------------------------------------------------

describe('useTableConfig — partial overrides', () => {
  it('merges partial overrides with defaults for missing keys', async () => {
    const customColumns = ['Account', 'AccountName'];

    mockGetParameters.mockResolvedValue(
      buildResponse([
        { key: 'chart_of_accounts.columns', value: customColumns },
        // filterable_columns, default_sort, page_size NOT provided
      ]),
    );

    const { result } = renderHook(() => useTableConfig('chart_of_accounts'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Overridden key uses API value
    expect(result.current.columns).toEqual(customColumns);
    // Missing keys fall back to defaults
    expect(result.current.filterableColumns).toEqual(DEFAULTS.chart_of_accounts.filterableColumns);
    expect(result.current.defaultSort).toEqual(DEFAULTS.chart_of_accounts.defaultSort);
    expect(result.current.pageSize).toEqual(DEFAULTS.chart_of_accounts.pageSize);
  });

  it('falls back to defaults for invalid JSON values', async () => {
    mockGetParameters.mockResolvedValue(
      buildResponse([
        { key: 'parameters.columns', value: 'not-valid-json[' },
        { key: 'parameters.default_sort', value: '{"invalid": true}' },
        { key: 'parameters.page_size', value: '-5' },
      ]),
    );

    const { result } = renderHook(() => useTableConfig('parameters'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // All invalid values fall back to defaults
    expect(result.current.columns).toEqual(DEFAULTS.parameters.columns);
    expect(result.current.defaultSort).toEqual(DEFAULTS.parameters.defaultSort);
    expect(result.current.pageSize).toEqual(DEFAULTS.parameters.pageSize);
  });

  it('falls back to defaults for empty array columns', async () => {
    mockGetParameters.mockResolvedValue(
      buildResponse([
        { key: 'banking_mutaties.columns', value: [] },
        { key: 'banking_mutaties.filterable_columns', value: [] },
      ]),
    );

    const { result } = renderHook(() => useTableConfig('banking_mutaties'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Empty arrays are not valid — fall back to defaults
    expect(result.current.columns).toEqual(DEFAULTS.banking_mutaties.columns);
    expect(result.current.filterableColumns).toEqual(DEFAULTS.banking_mutaties.filterableColumns);
  });
});
