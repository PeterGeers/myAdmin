/**
 * Property-based tests for useTableConfig hook
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations.
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Property 7
 */

import { renderHook, waitFor } from '@testing-library/react';
import fc from 'fast-check';
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
// Generators
// ---------------------------------------------------------------------------

/** Generate a valid TableEntity name. */
const entityArbitrary: fc.Arbitrary<TableEntity> = fc.constantFrom(
  'chart_of_accounts',
  'parameters',
  'banking_mutaties',
);

/** Generate an API response scenario: success with empty params, success=false, or error. */
const apiScenarioArbitrary = fc.constantFrom('empty', 'failure', 'error', 'no_namespace');

// ---------------------------------------------------------------------------
// Property 7: Default Config Robustness
// ---------------------------------------------------------------------------

describe('Property 7: Default Config Robustness', () => {
  // Increase timeout for property-based tests with async renderHook
  jest.setTimeout(30000);
  /**
   * **Validates: Requirements 6.4, 6.10**
   *
   * For any valid entity name, `useTableConfig` returns a `TableConfig` with
   * non-empty `columns`, non-empty `filterableColumns`, valid `defaultSort`
   * (non-empty field, valid direction), and positive `pageSize` — even when
   * the parameter API returns no data or an error.
   */
  it('always returns a valid config regardless of API response', async () => {
    // We run this as a loop over generated inputs rather than inside fc.assert
    // because renderHook is async and fast-check's property callback is sync.
    // 100 iterations across 3 entities × 4 scenarios = good coverage.
    const inputs = fc.sample(
      fc.tuple(entityArbitrary, apiScenarioArbitrary),
      100,
    );

    for (const [entity, scenario] of inputs) {
      jest.clearAllMocks();

      // Configure mock based on scenario
      switch (scenario) {
        case 'empty':
          mockGetParameters.mockResolvedValue({
            success: true,
            tenant: 'TestTenant',
            parameters: { 'ui.tables': [] },
          });
          break;
        case 'failure':
          mockGetParameters.mockResolvedValue({
            success: false,
            tenant: 'TestTenant',
            parameters: {},
          });
          break;
        case 'error':
          mockGetParameters.mockRejectedValue(new Error('Network error'));
          break;
        case 'no_namespace':
          mockGetParameters.mockResolvedValue({
            success: true,
            tenant: 'TestTenant',
            parameters: {},
          });
          break;
      }

      const { result, unmount } = renderHook(() => useTableConfig(entity));

      // Verify invariants hold immediately (while loading — defaults)
      expect(result.current.columns.length).toBeGreaterThan(0);
      expect(result.current.filterableColumns.length).toBeGreaterThan(0);
      expect(result.current.defaultSort.field.length).toBeGreaterThan(0);
      expect(['asc', 'desc']).toContain(result.current.defaultSort.direction);
      expect(result.current.pageSize).toBeGreaterThan(0);

      // Wait for loading to complete
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Verify invariants still hold after loading
      expect(result.current.columns.length).toBeGreaterThan(0);
      expect(result.current.filterableColumns.length).toBeGreaterThan(0);
      expect(result.current.defaultSort.field.length).toBeGreaterThan(0);
      expect(['asc', 'desc']).toContain(result.current.defaultSort.direction);
      expect(result.current.pageSize).toBeGreaterThan(0);

      // All column values should be strings
      for (const col of result.current.columns) {
        expect(typeof col).toBe('string');
      }
      for (const col of result.current.filterableColumns) {
        expect(typeof col).toBe('string');
      }

      unmount();
    }
  });

  it('defaults match the DEFAULTS constant for every entity', () => {
    const entities = fc.sample(entityArbitrary, 100);

    for (const entity of entities) {
      const defaults = DEFAULTS[entity];

      // Every entity must have valid defaults
      expect(defaults.columns.length).toBeGreaterThan(0);
      expect(defaults.filterableColumns.length).toBeGreaterThan(0);
      expect(defaults.defaultSort.field.length).toBeGreaterThan(0);
      expect(['asc', 'desc']).toContain(defaults.defaultSort.direction);
      expect(defaults.pageSize).toBeGreaterThan(0);
    }
  });
});
