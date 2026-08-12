/**
 * Unit tests for useAssetSearch hook
 *
 * @see .kiro/specs/Common/image-asset-management/design.md
 * Task: 8.2
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useAssetSearch } from '../useAssetSearch';
import { createMockResponse } from '@/test-utils/mockHelpers';
import type { AssetSearchResponse } from '@/types/mediaAsset';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

const mockSearchResponse: AssetSearchResponse = {
  success: true,
  data: [
    {
      id: 'ast_01H1234567890',
      original_filename: 'invoice_2024.pdf',
      mime_type: 'application/pdf',
      file_size: 245000,
      category: 'invoices',
      media_type: 'document',
      created_at: '2025-03-15T10:30:00Z',
      reference_count: 2,
      presigned_url: null,
    },
    {
      id: 'ast_01H9876543210',
      original_filename: 'logo.png',
      mime_type: 'image/png',
      file_size: 52000,
      category: 'branding',
      media_type: 'image',
      created_at: '2025-03-14T09:00:00Z',
      reference_count: 5,
      presigned_url: 'https://example.com/logo.png',
    },
  ],
  pagination: {
    page: 1,
    page_size: 20,
    total: 87,
    total_pages: 5,
  },
};

describe('useAssetSearch', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();

    // Setup auth mock
    mockFetchAuthSession.mockResolvedValue({
      tokens: {
        idToken: { toString: () => 'mock-jwt-token' },
      },
    } as any);

    // Setup localStorage mock
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('test-tenant');

    // Setup fetch mock
    fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      createMockResponse({ body: mockSearchResponse })
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('fetches assets on mount by default', async () => {
    const { result } = renderHook(() => useAssetSearch());

    // Initially loading
    expect(result.current.loading).toBe(true);
    expect(result.current.assets).toEqual([]);

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.assets).toHaveLength(2);
    expect(result.current.assets[0].id).toBe('ast_01H1234567890');
    expect(result.current.totalPages).toBe(5);
    expect(result.current.total).toBe(87);
    expect(result.current.page).toBe(1);
  });

  it('does not fetch on mount when fetchOnMount is false', async () => {
    const { result } = renderHook(() =>
      useAssetSearch({ fetchOnMount: false })
    );

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.assets).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('includes Authorization and X-Tenant headers in request', async () => {
    renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'X-Tenant': 'test-tenant',
        },
      })
    );
  });

  it('builds correct URL with search params', async () => {
    renderHook(() =>
      useAssetSearch({
        initialFilters: {
          q: 'invoice',
          category: 'invoices',
          media_type: 'document',
          sort: 'created_at',
          order: 'desc',
        },
      })
    );

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/api/media-assets/search?');
    expect(calledUrl).toContain('q=invoice');
    expect(calledUrl).toContain('category=invoices');
    expect(calledUrl).toContain('media_type=document');
    expect(calledUrl).toContain('sort=created_at');
    expect(calledUrl).toContain('order=desc');
    expect(calledUrl).toContain('page=1');
    expect(calledUrl).toContain('page_size=20');
  });

  it('sets error when not authenticated', async () => {
    mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.error).toBe('Not authenticated');
    expect(result.current.assets).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('handles HTTP error responses', async () => {
    fetchSpy.mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 500,
        body: { error: 'Internal server error' },
      })
    );

    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.error).toBe('Internal server error');
    expect(result.current.assets).toEqual([]);
  });

  it('handles network errors', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('Network failure'));

    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.error).toBe('Network failure');
    expect(result.current.assets).toEqual([]);
  });

  it('setPage triggers fetch with new page', async () => {
    const page2Response: AssetSearchResponse = {
      success: true,
      data: [{
        id: 'ast_page2',
        original_filename: 'page2.pdf',
        mime_type: 'application/pdf',
        file_size: 100000,
        category: 'invoices',
        media_type: 'document',
        created_at: '2025-03-10T08:00:00Z',
        reference_count: 1,
        presigned_url: null,
      }],
      pagination: { page: 2, page_size: 20, total: 87, total_pages: 5 },
    };

    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.page).toBe(1);

    fetchSpy.mockResolvedValueOnce(createMockResponse({ body: page2Response }));

    act(() => {
      result.current.setPage(2);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.page).toBe(2);
    expect(result.current.assets[0].id).toBe('ast_page2');
  });

  it('setFilters resets to page 1 and debounces text query', async () => {
    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Clear the initial fetch call
    fetchSpy.mockClear();

    const filteredResponse: AssetSearchResponse = {
      success: true,
      data: [{
        id: 'ast_filtered',
        original_filename: 'filtered.pdf',
        mime_type: 'application/pdf',
        file_size: 50000,
        category: 'invoices',
        media_type: 'document',
        created_at: '2025-03-12T08:00:00Z',
        reference_count: 0,
        presigned_url: null,
      }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    };

    fetchSpy.mockResolvedValueOnce(createMockResponse({ body: filteredResponse }));

    // Set filters with text query — should debounce
    act(() => {
      result.current.setFilters({ q: 'filtered', category: 'invoices' });
    });

    // Fetch should not have been called yet (debounced)
    expect(fetchSpy).not.toHaveBeenCalled();

    // Advance timers past debounce
    await act(async () => {
      vi.advanceTimersByTime(300);
      await vi.runAllTimersAsync();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(result.current.page).toBe(1);
    expect(result.current.assets[0].id).toBe('ast_filtered');
  });

  it('setFilters without text query fetches immediately', async () => {
    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    fetchSpy.mockClear();

    fetchSpy.mockResolvedValueOnce(createMockResponse({ body: mockSearchResponse }));

    // Set filters without q — should fetch immediately (no debounce)
    act(() => {
      result.current.setFilters({ category: 'branding' });
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('category=branding');
  });

  it('refresh re-fetches with current filters and page', async () => {
    const { result } = renderHook(() =>
      useAssetSearch({ initialFilters: { category: 'invoices' } })
    );

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    fetchSpy.mockClear();
    fetchSpy.mockResolvedValueOnce(createMockResponse({ body: mockSearchResponse }));

    act(() => {
      result.current.refresh();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('category=invoices');
    expect(calledUrl).toContain('page=1');
  });

  it('uses initial filters on first fetch', async () => {
    renderHook(() =>
      useAssetSearch({
        initialFilters: {
          category: 'branding',
          media_type: 'image',
          page_size: 10,
        },
      })
    );

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('category=branding');
    expect(calledUrl).toContain('media_type=image');
    expect(calledUrl).toContain('page_size=10');
  });

  it('does not include empty filter values in URL params', async () => {
    renderHook(() =>
      useAssetSearch({
        initialFilters: { q: '', category: '', media_type: '' },
      })
    );

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).not.toContain('q=');
    expect(calledUrl).not.toContain('category=');
    expect(calledUrl).not.toContain('media_type=');
  });

  it('aborts previous request when new one is triggered', async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort');

    const { result } = renderHook(() => useAssetSearch());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    fetchSpy.mockResolvedValue(createMockResponse({ body: mockSearchResponse }));

    // Trigger multiple rapid page changes
    act(() => {
      result.current.setPage(2);
    });

    act(() => {
      result.current.setPage(3);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Previous request should have been aborted
    expect(abortSpy).toHaveBeenCalled();
    abortSpy.mockRestore();
  });
});
