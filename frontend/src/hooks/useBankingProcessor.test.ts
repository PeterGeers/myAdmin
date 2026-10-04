/**
 * Tests for useBankingProcessor — the orchestrator that composes
 * useBankingState + useBankingUpload + useBankingPatterns.
 *
 * Focuses on the composition contract: the merged API surface is exposed
 * and the re-exported utilities behave. apiService + context hooks mocked.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useBankingProcessor, formatAmount } from './useBankingProcessor';

vi.mock('../services/apiService');
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);

vi.mock('../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'GoodwinSolutions' }),
}));
vi.mock('./useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (k: string) => k, i18n: { language: 'nl' } }),
}));
vi.mock('./useAccountLookup', () => ({
  useAccountLookup: () => ({ accounts: [] }),
}));

describe('useBankingProcessor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockGet.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          accounts: [],
          descriptions: [],
          bank_accounts: [],
          credit_card_accounts: [],
          exchange_rate_account: null,
        },
      }),
    );
  });

  it('exposes the merged state + upload + patterns API surface', async () => {
    const { result } = renderHook(() => useBankingProcessor());

    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    // state
    expect(result.current.transactions).toEqual([]);
    expect(typeof result.current.setTransactions).toBe('function');
    // upload
    expect(typeof result.current.handleSaveTransactions).toBe('function');
    expect(typeof result.current.confirmSaveTransactions).toBe('function');
    // patterns
    expect(typeof result.current.applyPatterns).toBe('function');
    expect(result.current.patternResults).toBeNull();
    // utility re-exports
    expect(typeof result.current.formatAmount).toBe('function');
    expect(typeof result.current.mapLookupData).toBe('function');
  });

  it('re-exports formatAmount working identically', () => {
    expect(formatAmount(1000)).toBe('€1.000,00');
  });

  it('wires upload save-confirmation flow through the composed hook', async () => {
    const { result } = renderHook(() => useBankingProcessor());
    await waitFor(() => expect(mockGet).toHaveBeenCalled());

    act(() => {
      result.current.handleSaveTransactions();
    });
    expect(result.current.showSaveConfirmation).toBe(true);

    mockPost.mockResolvedValue(
      createMockResponse({ body: { success: true, saved_count: 0, table: 'x' } }),
    );
    await act(async () => {
      await result.current.confirmSaveTransactions();
    });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/banking/save-transactions',
      expect.objectContaining({ test_mode: false }),
    );
  });
});
