/**
 * Tests for useCheckReference hook.
 *
 * Covers filter-options fetch, check-reference summary fetch (incl. the
 * amount filter that drops near-zero rows), reference-detail drill-down,
 * and error branches. apiService + context hooks mocked.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { authenticatedGet } from '@/services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useCheckReference } from './useCheckReference';

vi.mock('@/services/apiService');
const mockGet = vi.mocked(authenticatedGet);

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

function defaultGet(url: string) {
  if (url.includes('/api/reports/filter-options')) {
    return Promise.resolve(
      createMockResponse({ body: { success: true, ledgers: ['L1'], references: ['R1'] } }),
    );
  }
  return Promise.resolve(createMockResponse({ body: { success: true, summary: [], transactions: [] } }));
}

describe('useCheckReference', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation(defaultGet as never);
  });

  it('fetches filter options on mount and populates ledgers/references', async () => {
    const { result } = renderHook(() => useCheckReference());

    await waitFor(() => {
      expect(result.current.availableLedgers).toEqual(['L1']);
    });
    expect(result.current.availableReferences).toEqual(['R1']);
    const url = mockGet.mock.calls.find((c) => String(c[0]).includes('filter-options'))?.[0];
    expect(String(url)).toContain('administration=GoodwinSolutions');
  });

  it('fetchCheckRefData keeps only rows with |total_amount| > 0.01', async () => {
    const { result } = renderHook(() => useCheckReference());
    await waitFor(() => expect(result.current.availableLedgers.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(
        createMockResponse({
          body: {
            success: true,
            summary: [
              { ReferenceNumber: 'A', total_amount: '0.00' },
              { ReferenceNumber: 'B', total_amount: '150.25' },
              { ReferenceNumber: 'C', total_amount: 0.005 },
            ],
          },
        }),
      ),
    );

    await act(async () => {
      await result.current.fetchCheckRefData();
    });

    expect(result.current.refSummaryData).toHaveLength(1);
    expect(result.current.refSummaryData[0].ReferenceNumber).toBe('B');
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
  });

  it('fetchCheckRefData shows an error toast on an unsuccessful response', async () => {
    const { result } = renderHook(() => useCheckReference());
    await waitFor(() => expect(result.current.availableLedgers.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(createMockResponse({ body: { success: false, error: 'bad' } })),
    );

    await act(async () => {
      await result.current.fetchCheckRefData();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
  });

  it('fetchCheckRefData shows an error toast when the request rejects', async () => {
    const { result } = renderHook(() => useCheckReference());
    await waitFor(() => expect(result.current.availableLedgers.length).toBe(1));

    mockGet.mockImplementationOnce(() => Promise.reject(new Error('offline')));

    await act(async () => {
      await result.current.fetchCheckRefData();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
    expect(result.current.loading).toBe(false);
  });

  it('fetchReferenceDetails loads the drill-down transactions and sets selection', async () => {
    const { result } = renderHook(() => useCheckReference());
    await waitFor(() => expect(result.current.availableLedgers.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(
        createMockResponse({ body: { success: true, transactions: [{ TransactionNumber: 'T1' }] } }),
      ),
    );

    await act(async () => {
      await result.current.fetchReferenceDetails('R1');
    });

    expect(result.current.selectedReference).toBe('R1');
    expect(result.current.selectedReferenceDetails).toHaveLength(1);
    const url = mockGet.mock.calls.find((c) => String(c[0]).includes('check-reference'))?.[0];
    expect(String(url)).toContain('referenceNumber=R1');
  });
});
