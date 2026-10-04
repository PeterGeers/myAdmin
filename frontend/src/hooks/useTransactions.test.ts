/**
 * Tests for useTransactions (Mutaties page) hook.
 *
 * Covers mutaties/filter-options fetch, modal open handlers, save record
 * (insert vs update endpoint selection + error branch), Ref3 click handling
 * (gdrive link, presigned-url lookup, clipboard fallback), and clipboard copy.
 * apiService + context hooks mocked.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { authenticatedGet, authenticatedPost } from '@/services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useTransactions } from './useTransactions';
import type { Transaction } from '@/components/BankingProcessor.types';

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
vi.mock('@/hooks/useAccountLookup', () => ({
  useAccountLookup: () => ({ accounts: [] }),
}));

function defaultGet(url: string) {
  if (url.startsWith('/api/banking/filter-options')) {
    return Promise.resolve(
      createMockResponse({ body: { success: true, years: ['2025'], administrations: ['T'] } }),
    );
  }
  if (url.startsWith('/api/banking/mutaties')) {
    return Promise.resolve(
      createMockResponse({ body: { success: true, mutaties: [{ ID: 1 }] } }),
    );
  }
  return Promise.resolve(createMockResponse({ body: { success: true } }));
}

const record = (over: Partial<Transaction> = {}): Transaction =>
  ({ ID: 1, row_id: 1, TransactionAmount: 0, Administration: 'T', Ref3: '', ...over }) as Transaction;

describe('useTransactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('selectedTenant', 'GoodwinSolutions');
    mockGet.mockImplementation(defaultGet as never);
  });

  it('fetches mutaties and filter options on mount', async () => {
    const { result } = renderHook(() => useTransactions());

    await waitFor(() => {
      expect(result.current.mutaties).toEqual([{ ID: 1 }]);
    });
    expect(result.current.filterOptions.years).toEqual(['2025']);
    const url = mockGet.mock.calls.find((c) => String(c[0]).includes('/mutaties'))?.[0];
    expect(String(url)).toContain('administration=GoodwinSolutions');
  });

  it('does not fetch mutaties when no tenant is stored', async () => {
    localStorage.clear();
    renderHook(() => useTransactions());

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith('/api/banking/filter-options');
    });
    const mutatieCall = mockGet.mock.calls.find((c) => String(c[0]).includes('/mutaties'));
    expect(mutatieCall).toBeUndefined();
  });

  it('openInsertModal seeds a blank record in insert mode', async () => {
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    act(() => result.current.openInsertModal());

    expect(result.current.isInsertMode).toBe(true);
    expect(result.current.isOpen).toBe(true);
    expect(result.current.editingRecord?.Administration).toBe('GoodwinSolutions');
  });

  it('handleSaveRecord uses the update endpoint when editing', async () => {
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    act(() => result.current.openEditModal(record({ ID: 5 })));
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));

    await act(async () => {
      await result.current.handleSaveRecord();
    });

    expect(mockPost).toHaveBeenCalledWith('/api/banking/update-mutatie', expect.objectContaining({ ID: 5 }));
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
  });

  it('handleSaveRecord uses the insert endpoint in insert mode', async () => {
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    act(() => result.current.openInsertModal());
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));

    await act(async () => {
      await result.current.handleSaveRecord();
    });

    expect(mockPost).toHaveBeenCalledWith('/api/banking/insert-mutatie', expect.anything());
  });

  it('handleSaveRecord sets modal error on unsuccessful save', async () => {
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    act(() => result.current.openEditModal(record()));
    mockPost.mockResolvedValue(createMockResponse({ body: { success: false, error: 'bad' } }));

    await act(async () => {
      await result.current.handleSaveRecord();
    });

    expect(result.current.modalError).toBe('bad');
  });

  it('handleSaveRecord sets modal error when the request rejects', async () => {
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    act(() => result.current.openEditModal(record()));
    mockPost.mockRejectedValue(new Error('offline'));

    await act(async () => {
      await result.current.handleSaveRecord();
    });

    expect(result.current.modalError).toContain('messages.errorUpdating');
  });

  it('handleRef3Click opens a Google Drive link in a new tab', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    await act(async () => {
      await result.current.handleRef3Click('https://drive.google.com/file/123');
    });

    expect(openSpy).toHaveBeenCalledWith('https://drive.google.com/file/123', '_blank');
    openSpy.mockRestore();
  });

  it('handleRef3Click resolves a storage key via presigned-url and opens it', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(createMockResponse({ body: { success: true, url: 'https://signed/x' } })),
    );

    await act(async () => {
      await result.current.handleRef3Click('invoices/2025/file.pdf');
    });

    const url = mockGet.mock.calls.find((c) => String(c[0]).includes('presigned-url'))?.[0];
    expect(String(url)).toContain('key=invoices');
    expect(openSpy).toHaveBeenCalledWith('https://signed/x', '_blank');
    openSpy.mockRestore();
  });

  it('handleRef3Click falls back to clipboard when the key cannot be resolved', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(createMockResponse({ body: { success: false } })),
    );

    await act(async () => {
      await result.current.handleRef3Click('some/key.pdf');
    });

    expect(writeText).toHaveBeenCalledWith('some/key.pdf');
  });

  it('copyToClipboard writes text and shows an info toast', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const { result } = renderHook(() => useTransactions());
    await waitFor(() => expect(result.current.mutaties.length).toBe(1));

    await act(async () => {
      result.current.copyToClipboard('hello');
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledWith('hello');
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'info' }));
  });
});
