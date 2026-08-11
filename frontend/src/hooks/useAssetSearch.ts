/**
 * useAssetSearch Hook
 *
 * Reusable hook for searching and paginating media assets via GET /api/assets/search.
 * Handles debounced text queries, filter state, pagination, and authentication.
 *
 * Used by AssetPicker and other components that need asset search/browse.
 *
 * @module hooks/useAssetSearch
 * @see .kiro/specs/Common/image-asset-management/design.md
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '@/config';
import type {
  MediaAsset,
  AssetSearchFilters,
  AssetSearchResponse,
  AssetPagination,
} from '@/types/mediaAsset';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UseAssetSearchOptions {
  /** Initial/default filters to apply on first fetch */
  initialFilters?: AssetSearchFilters;
  /** Debounce delay for text query in ms (default: 300) */
  debounceMs?: number;
  /** Whether to fetch immediately on mount (default: true) */
  fetchOnMount?: boolean;
}

export interface UseAssetSearchReturn {
  /** Current list of assets from the latest search */
  assets: MediaAsset[];
  /** Whether a fetch is in progress */
  loading: boolean;
  /** Error message, or null if no error */
  error: string | null;
  /** Current page number (1-indexed) */
  page: number;
  /** Total number of pages */
  totalPages: number;
  /** Total number of matching assets */
  total: number;
  /** Set the current page (triggers a fetch) */
  setPage: (page: number) => void;
  /** Update filters (resets to page 1 and triggers a fetch) */
  setFilters: (filters: AssetSearchFilters) => void;
  /** Manually re-fetch with current filters and page */
  refresh: () => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_PAGE_SIZE = 20;
const DEFAULT_DEBOUNCE_MS = 300;

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAssetSearch(options: UseAssetSearchOptions = {}): UseAssetSearchReturn {
  const {
    initialFilters = {},
    debounceMs = DEFAULT_DEBOUNCE_MS,
    fetchOnMount = true,
  } = options;

  // State
  const [filters, setFiltersState] = useState<AssetSearchFilters>(initialFilters);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [page, setPageState] = useState<number>(initialFilters.page ?? 1);
  const [pagination, setPagination] = useState<AssetPagination>({
    page: 1,
    page_size: initialFilters.page_size ?? DEFAULT_PAGE_SIZE,
    total: 0,
    total_pages: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs for debounce and abort
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  // Track whether this is the initial mount
  const hasFetchedRef = useRef(false);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // ── Core fetch function ─────────────────────────────────────────────────

  const fetchAssets = useCallback(async (searchFilters: AssetSearchFilters, searchPage: number) => {
    // Abort any in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      if (!token) {
        if (mountedRef.current) {
          setError('Not authenticated');
          setLoading(false);
        }
        return;
      }

      const params = new URLSearchParams();
      if (searchFilters.q) params.set('q', searchFilters.q);
      if (searchFilters.category) params.set('category', searchFilters.category);
      if (searchFilters.media_type) params.set('media_type', searchFilters.media_type);
      if (searchFilters.sort) params.set('sort', searchFilters.sort);
      if (searchFilters.order) params.set('order', searchFilters.order);
      params.set('page', String(searchPage));
      params.set('page_size', String(searchFilters.page_size ?? DEFAULT_PAGE_SIZE));

      const url = buildApiUrl('/api/assets/search', params);

      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': localStorage.getItem('selectedTenant') || '',
        },
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.error || `HTTP ${response.status}`);
      }

      const result: AssetSearchResponse = await response.json();

      if (mountedRef.current) {
        setAssets(result.data);
        setPagination(result.pagination);
      }
    } catch (err) {
      // Don't treat abort as an error
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch assets');
        setAssets([]);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  // ── Debounced search trigger for text query changes ─────────────────────

  const debouncedFetch = useCallback((searchFilters: AssetSearchFilters, searchPage: number) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchAssets(searchFilters, searchPage);
    }, debounceMs);
  }, [fetchAssets, debounceMs]);

  // ── Public setters ──────────────────────────────────────────────────────

  const setFilters = useCallback((newFilters: AssetSearchFilters) => {
    setFiltersState(newFilters);
    setPageState(1);
    // Debounce if text query changed, otherwise fetch immediately
    if (newFilters.q !== undefined) {
      debouncedFetch(newFilters, 1);
    } else {
      fetchAssets(newFilters, 1);
    }
  }, [debouncedFetch, fetchAssets]);

  const setPage = useCallback((newPage: number) => {
    setPageState(newPage);
    fetchAssets(filters, newPage);
  }, [filters, fetchAssets]);

  const refresh = useCallback(() => {
    fetchAssets(filters, page);
  }, [filters, page, fetchAssets]);

  // ── Fetch on mount ──────────────────────────────────────────────────────

  useEffect(() => {
    if (fetchOnMount && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchAssets(filters, page);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Return ──────────────────────────────────────────────────────────────

  return {
    assets,
    loading,
    error,
    page,
    totalPages: pagination.total_pages,
    total: pagination.total,
    setPage,
    setFilters,
    refresh,
  };
}
