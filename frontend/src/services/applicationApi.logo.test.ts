/**
 * Tests for `fetchPublicLogo` (spec 13, task 5.1/5.2) — the public, unauthenticated Flask-plane
 * read of a tenant's ONE branding logo for the public application form (R5).
 *
 * `global.fetch` is mocked. These pin:
 *  - the URL shaping (`{baseUrl}/api/public/landing/{slug}/logo`, trailing slash normalised, slug
 *    encoded);
 *  - the `{ success, data: { logo } }` envelope unwrap → the data-URI string on a configured logo;
 *  - the graceful "no logo" path (R5.3): `logo: null`, a non-ok status, a network error, and an
 *    aborted fetch all resolve to `null` — a missing logo NEVER throws or blocks the form.
 */

import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest';
import { fetchPublicLogo } from './applicationApi';
import { createMockResponse } from '@/test-utils/mockHelpers';

const BASE = 'https://flask.test';
const DATA_URI = 'data:image/png;base64,AAAA';

describe('fetchPublicLogo', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('requests {baseUrl}/api/public/landing/{slug}/logo (slug encoded)', async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ body: { success: true, data: { logo: null } } }),
    );

    await fetchPublicLogo('h-dcn', { baseUrl: BASE });

    expect(fetch).toHaveBeenCalledWith(
      `${BASE}/api/public/landing/h-dcn/logo`,
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('normalises a trailing slash on the base URL', async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ body: { success: true, data: { logo: null } } }),
    );

    await fetchPublicLogo('acme', { baseUrl: `${BASE}/` });

    expect(fetch).toHaveBeenCalledWith(
      `${BASE}/api/public/landing/acme/logo`,
      expect.anything(),
    );
  });

  it('returns the data-URI string when the tenant has a configured logo', async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ body: { success: true, data: { logo: DATA_URI } } }),
    );

    const result = await fetchPublicLogo('acme', { baseUrl: BASE });

    expect(result).toBe(DATA_URI);
  });

  it('returns null when the logo is unconfigured (data.logo === null) — graceful absence (R5.3)', async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ body: { success: true, data: { logo: null } } }),
    );

    const result = await fetchPublicLogo('acme', { baseUrl: BASE });

    expect(result).toBeNull();
  });

  it('returns null on a non-ok status (unknown slug / server error) without throwing (R5.3)', async () => {
    vi.mocked(fetch).mockResolvedValue(createMockResponse({ ok: false, status: 404 }));

    const result = await fetchPublicLogo('missing', { baseUrl: BASE });

    expect(result).toBeNull();
  });

  it('returns null on a network/parse error without throwing (R5.3)', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('network down'));

    const result = await fetchPublicLogo('acme', { baseUrl: BASE });

    expect(result).toBeNull();
  });

  it('returns null when the fetch is aborted (unmount) rather than throwing', async () => {
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    vi.mocked(fetch).mockRejectedValue(abortError);
    const controller = new AbortController();

    const result = await fetchPublicLogo('acme', { baseUrl: BASE, signal: controller.signal });

    expect(result).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      `${BASE}/api/public/landing/acme/logo`,
      expect.objectContaining({ signal: controller.signal }),
    );
  });
});
