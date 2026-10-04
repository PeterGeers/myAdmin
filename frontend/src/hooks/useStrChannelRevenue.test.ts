/**
 * Tests for useStrChannelRevenue hook.
 *
 * Covers the visibility gate, preview fetch, revenue calculation, save flow
 * (incl. clearing of generated transactions), request shaping, and the error
 * branches for each API call. apiService + context hooks mocked.
 */

import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { authenticatedGet, authenticatedPost } from '@/services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useStrChannelRevenue } from './useStrChannelRevenue';

vi.mock('@/services/apiService');
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);

const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@chakra-ui/react');
  return { ...actual, useToast: () => mockToast };
});

vi.mock('@/context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'GoodwinSolutions' }),
}));
vi.mock('@/hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (k: string) => k, i18n: { language: 'nl' } }),
}));

const mockHasFunction = vi.fn();
vi.mock('@/hooks/useTenantFunctions', () => ({
  useTenantFunctions: () => ({ hasFunction: mockHasFunction }),
}));

describe('useStrChannelRevenue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasFunction.mockReturnValue(true);
  });

  it('exposes isVisible from the str_channel_revenue tenant function flag', () => {
    mockHasFunction.mockReturnValue(false);
    const { result } = renderHook(() => useStrChannelRevenue());
    expect(result.current.isVisible).toBe(false);
    expect(mockHasFunction).toHaveBeenCalledWith('str_channel_revenue');
  });

  it('seeds filters with the current tenant and current year/month', () => {
    const { result } = renderHook(() => useStrChannelRevenue());
    expect(result.current.strChannelFilters.administration).toBe('GoodwinSolutions');
    expect(result.current.strChannelFilters.year).toBe(new Date().getFullYear());
  });

  it('fetchStrChannelPreview shapes the request and stores preview rows', async () => {
    mockGet.mockResolvedValue(
      createMockResponse({ body: { success: true, preview_data: [{ ReferenceNumber: 'R1' }] } }),
    );
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.fetchStrChannelPreview();
    });

    expect(result.current.strChannelPreview).toHaveLength(1);
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('/api/str-channel/preview?');
    expect(url).toContain('administration=GoodwinSolutions');
    expect(url).toContain('test_mode=false');
  });

  it('fetchStrChannelPreview shows an error toast on unsuccessful response', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: false, error: 'x' } }));
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.fetchStrChannelPreview();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
    expect(result.current.strChannelPreview).toEqual([]);
  });

  it('fetchStrChannelPreview shows an error toast when the request rejects', async () => {
    mockGet.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.fetchStrChannelPreview();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
    expect(result.current.loading).toBe(false);
  });

  it('calculateStrChannelRevenue posts the filter payload and stores results', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({
        body: { success: true, transactions: [{ TransactionAmount: 10 }], summary: { ref1: 'x', month: 1, year: 2025, end_date: '2025-01-31' } },
      }),
    );
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.calculateStrChannelRevenue();
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/str-channel/calculate',
      expect.objectContaining({ administration: 'GoodwinSolutions', test_mode: false }),
    );
    expect(result.current.strChannelTransactions).toHaveLength(1);
    expect(result.current.strChannelSummary?.ref1).toBe('x');
  });

  it('calculateStrChannelRevenue shows an error toast when the request rejects', async () => {
    mockPost.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.calculateStrChannelRevenue();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
  });

  it('saveStrChannelTransactions clears generated state on success', async () => {
    // First calculate to populate transactions
    mockPost.mockResolvedValueOnce(
      createMockResponse({
        body: { success: true, transactions: [{ TransactionAmount: 10 }], summary: { ref1: 'x', month: 1, year: 2025, end_date: '2025-01-31' } },
      }),
    );
    const { result } = renderHook(() => useStrChannelRevenue());
    await act(async () => {
      await result.current.calculateStrChannelRevenue();
    });
    expect(result.current.strChannelTransactions).toHaveLength(1);

    mockPost.mockResolvedValueOnce(
      createMockResponse({ body: { success: true, saved_count: 1 } }),
    );
    await act(async () => {
      await result.current.saveStrChannelTransactions();
    });

    expect(mockPost).toHaveBeenLastCalledWith(
      '/api/str-channel/save',
      expect.objectContaining({ test_mode: false }),
    );
    expect(result.current.strChannelTransactions).toEqual([]);
    expect(result.current.strChannelSummary).toBeNull();
  });

  it('saveStrChannelTransactions shows an error toast on unsuccessful response', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: false, error: 'nope' } }));
    const { result } = renderHook(() => useStrChannelRevenue());

    await act(async () => {
      await result.current.saveStrChannelTransactions();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
  });
});
