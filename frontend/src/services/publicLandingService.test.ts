/**
 * Tests for publicLandingService — the public, unauthenticated CloudFront/S3
 * fetch of a tenant's published landing.json. global.fetch is mocked; these
 * assert the URL shaping (base URL + slug + landing.json), the status→result
 * mapping (404/403 → not_found, other non-ok → error, ok → success), and the
 * network-error branch. This is the behavior migrated out of PublicLandingPage
 * when the raw inline fetch moved into the service layer.
 */

import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest';
import { fetchLandingData, getCloudFrontBaseUrl } from './publicLandingService';
import { createMockResponse } from '@/test-utils/mockHelpers';

const BASE = 'https://cdn.example.com';

describe('publicLandingService', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('getCloudFrontBaseUrl', () => {
    it('uses the configured env URL (trailing slash trimmed), else the current origin', () => {
      // Mirrors the implementation: prefer VITE_CLOUDFRONT_PUBLIC_PAGES_URL when
      // set (dropping any trailing slash), otherwise fall back to the origin.
      const envUrl = import.meta.env.VITE_CLOUDFRONT_PUBLIC_PAGES_URL;
      const expected = envUrl
        ? envUrl.replace(/\/$/, '')
        : window.location.origin;
      expect(getCloudFrontBaseUrl()).toBe(expected);
    });
  });

  describe('fetchLandingData', () => {
    it('requests {baseUrl}/{slug}/landing.json', async () => {
      vi.mocked(fetch).mockResolvedValue(
        createMockResponse({ body: { tenant_slug: 'acme', sections: [] } }),
      );

      await fetchLandingData('acme', { baseUrl: BASE });

      expect(fetch).toHaveBeenCalledWith(
        `${BASE}/acme/landing.json`,
        expect.objectContaining({ signal: undefined }),
      );
    });

    it('returns success with the parsed data on 200', async () => {
      const data = { tenant_slug: 'acme', version: 2, sections: [{ id: 'a' }] };
      vi.mocked(fetch).mockResolvedValue(createMockResponse({ body: data }));

      const result = await fetchLandingData('acme', { baseUrl: BASE });

      expect(result).toEqual({ status: 'success', data });
    });

    it('maps 404 to not_found', async () => {
      vi.mocked(fetch).mockResolvedValue(createMockResponse({ ok: false, status: 404 }));

      const result = await fetchLandingData('missing', { baseUrl: BASE });

      expect(result).toEqual({ status: 'not_found' });
    });

    it('maps 403 to not_found', async () => {
      vi.mocked(fetch).mockResolvedValue(createMockResponse({ ok: false, status: 403 }));

      const result = await fetchLandingData('forbidden', { baseUrl: BASE });

      expect(result).toEqual({ status: 'not_found' });
    });

    it('maps other non-ok statuses to error with the status in the message', async () => {
      vi.mocked(fetch).mockResolvedValue(createMockResponse({ ok: false, status: 500 }));

      const result = await fetchLandingData('acme', { baseUrl: BASE });

      expect(result).toEqual({ status: 'error', message: 'Failed to load page (500)' });
    });

    it('maps a thrown/network error to a generic error result', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('network down'));

      const result = await fetchLandingData('acme', { baseUrl: BASE });

      expect(result).toEqual({ status: 'error', message: 'Failed to load page' });
    });

    it('forwards an AbortSignal to fetch', async () => {
      vi.mocked(fetch).mockResolvedValue(createMockResponse({ body: { sections: [] } }));
      const controller = new AbortController();

      await fetchLandingData('acme', { baseUrl: BASE, signal: controller.signal });

      expect(fetch).toHaveBeenCalledWith(
        `${BASE}/acme/landing.json`,
        expect.objectContaining({ signal: controller.signal }),
      );
    });
  });
});
