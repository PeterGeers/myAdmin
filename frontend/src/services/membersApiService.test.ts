/**
 * Members API Service - Unit Tests
 *
 * Focused on the envelope-unwrapping + member-flattening behaviour: the module
 * wraps every 2xx body as `{ data: <result> }` and member records are NESTED
 * (`personal`/`membership`/`scope_values`). The service normalises both so the
 * page's flat-shape reads resolve.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { getCurrentAuthTokens } from './authService';
import {
  listMembers,
  searchMembers,
  getMember,
  createMember,
  updateMember,
  deleteMember,
  exportMembers,
  getFieldConfig,
  listMembershipTypes,
  createMembership,
  transitionMembership,
  bulkTransition,
} from './membersApiService';

// Mock the auth seam so no AWS Amplify session is needed.
vi.mock('./authService', () => ({
  getCurrentAuthTokens: vi.fn(),
}));

const mockGetTokens = vi.mocked(getCurrentAuthTokens);

describe('membersApiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // A configured base URL (fail-fast otherwise) + a valid bearer token.
    vi.stubEnv('VITE_MEMBERS_API_BASE_URL', 'http://members.test/api');
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'acc' } as never);
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  describe('listMembers', () => {
    it('unwraps the {data:[...]} envelope and flattens nested member records', async () => {
      const enveloped = {
        data: [
          {
            member_id: 'M-1',
            personal: { name: 'Jan Jansen', contact: 'm-1@h-dcn.example' },
            membership: {
              member_number: '1001',
              membership_type: 'regulier',
              status: 'active',
            },
            scope_values: { region: ['Noord'] },
          },
        ],
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: enveloped }),
      );

      const rows = await listMembers();

      expect(rows).toEqual([
        {
          member_id: 'M-1',
          name: 'Jan Jansen',
          email: 'm-1@h-dcn.example',
          status: 'active',
          membership_type: 'regulier',
          member_number: '1001',
          region: 'Noord',
        },
      ]);
      // Nested containers must not leak through and shadow the flat keys.
      expect(rows[0]).not.toHaveProperty('personal');
      expect(rows[0]).not.toHaveProperty('membership');
      expect(rows[0]).not.toHaveProperty('scope_values');
    });

    it('returns [] when the enveloped data is not an array', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: null } }),
      );
      await expect(listMembers()).resolves.toEqual([]);
    });

    it('leaves region undefined when scope_values.region is empty', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: { data: [{ member_id: 'M-2', scope_values: { region: [] } }] },
        }),
      );
      const rows = await listMembers();
      expect(rows[0].region).toBeUndefined();
    });
  });

  describe('getMember', () => {
    it('unwraps and flattens a single nested member record', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: {
            data: {
              member_id: 'M-9',
              personal: { name: 'Piet', contact: 'piet@h-dcn.example' },
              membership: { membership_type: 'student', status: 'pending' },
              scope_values: { region: ['Zuid'] },
            },
          },
        }),
      );

      const member = await getMember('M-9');

      expect(member).toMatchObject({
        member_id: 'M-9',
        name: 'Piet',
        email: 'piet@h-dcn.example',
        status: 'pending',
        membership_type: 'student',
        region: 'Zuid',
      });
    });
  });

  describe('getFieldConfig', () => {
    it('unwraps the enveloped field config', async () => {
      const cfg = { fields: [{ key: 'name' }], dimensions: [] };
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: cfg } }),
      );
      await expect(getFieldConfig()).resolves.toEqual(cfg);
    });
  });
});

// ============================================================================
// Task 16.4 — per-wrapper method/path/headers + 401 refresh-retry (R10.7)
//
// The established suite mocks the `fetch` + `getCurrentAuthTokens` seams
// directly (via createMockResponse) rather than MSW. We stay consistent with
// that: direct fetch mocking lets us assert the EXACT request the wrapper issues
// (method, URL, and the Bearer/X-Tenant/X-Language header set) without spinning
// up a service worker. The repo does ship `msw`, but matching the sibling
// tests' seam-mock style keeps the file coherent.
// ============================================================================

const BASE = 'http://members.test/api';

/** Grab the args of the Nth (default: last) fetch call: [url, init]. */
function fetchCall(index = -1): [string, RequestInit] {
  const calls = vi.mocked(global.fetch).mock.calls;
  const call = index < 0 ? calls[calls.length + index] : calls[index];
  return call as unknown as [string, RequestInit];
}

/** Normalise a HeadersInit (plain object here) to a lookup record. */
function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers ?? {}) as Record<string, string>;
}

describe('membersApiService — wrapper method/path/headers (task 16.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('VITE_MEMBERS_API_BASE_URL', BASE);
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'acc' } as never);
    global.fetch = vi.fn();
    // Default OK envelope for wrappers that don't care about the body shape.
    vi.mocked(global.fetch).mockResolvedValue(
      createMockResponse({ body: { data: {} } }),
    );
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  // ---- header semantics -----------------------------------------------------

  it('sends Authorization: Bearer <idToken> and X-Language on every request', async () => {
    localStorage.setItem('i18nextLng', 'en');
    await listMembers();

    const [, init] = fetchCall();
    const headers = headersOf(init);
    expect(headers.Authorization).toBe('Bearer tok');
    expect(headers['X-Language']).toBe('en');
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('defaults X-Language to nl when none is set', async () => {
    await listMembers();
    expect(headersOf(fetchCall()[1])['X-Language']).toBe('nl');
  });

  it('adds X-Tenant when a tenant is selected in localStorage', async () => {
    localStorage.setItem('selectedTenant', 'h-dcn');
    await listMembers();
    expect(headersOf(fetchCall()[1])['X-Tenant']).toBe('h-dcn');
  });

  it('omits X-Tenant when no tenant is set', async () => {
    await listMembers();
    expect(headersOf(fetchCall()[1])).not.toHaveProperty('X-Tenant');
  });

  // ---- per-wrapper method + path -------------------------------------------

  it('listMembers → GET /members', async () => {
    await listMembers();
    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${BASE}/members`);
  });

  it('searchMembers → POST /members/search with the filters body', async () => {
    const filters = { region: 'Noord' };
    await searchMembers(filters);
    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${BASE}/members/search`);
    expect(init.body).toBe(JSON.stringify(filters));
  });

  it('getMember → GET /members/{id} (id url-encoded)', async () => {
    await getMember('M/9');
    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${BASE}/members/M%2F9`);
  });

  it('createMember → POST /members with the body', async () => {
    const body = { name: 'New' };
    await createMember(body);
    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${BASE}/members`);
    expect(init.body).toBe(JSON.stringify(body));
  });

  it('updateMember → PUT /members/{id} with the body', async () => {
    const body = { name: 'Edit' };
    await updateMember('M-1', body);
    const [url, init] = fetchCall();
    expect(init.method).toBe('PUT');
    expect(url).toBe(`${BASE}/members/M-1`);
    expect(init.body).toBe(JSON.stringify(body));
  });

  it('deleteMember → DELETE /members/{id}', async () => {
    await deleteMember('M-1');
    const [url, init] = fetchCall();
    expect(init.method).toBe('DELETE');
    expect(url).toBe(`${BASE}/members/M-1`);
  });

  it('exportMembers → GET /members/export', async () => {
    await exportMembers();
    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${BASE}/members/export`);
  });

  it('getFieldConfig → GET /members/field-config', async () => {
    await getFieldConfig();
    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${BASE}/members/field-config`);
  });

  it('listMembershipTypes → GET /membership-types', async () => {
    await listMembershipTypes();
    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${BASE}/membership-types`);
  });

  it('listMembershipTypes(true) → GET /membership-types?active_only=true', async () => {
    await listMembershipTypes(true);
    const [url] = fetchCall();
    expect(url).toBe(`${BASE}/membership-types?active_only=true`);
  });

  it('createMembership → POST /members/{id}/memberships with the body', async () => {
    const body = { membership_type: 'regulier' };
    await createMembership('M-1', body);
    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${BASE}/members/M-1/memberships`);
    expect(init.body).toBe(JSON.stringify(body));
  });

  it('transitionMembership → POST /members/{id}/memberships/{mid}/transition', async () => {
    const body = { target: 'active' };
    await transitionMembership('M-1', 'MS-2', body);
    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${BASE}/members/M-1/memberships/MS-2/transition`);
    expect(init.body).toBe(JSON.stringify(body));
  });

  it('bulkTransition → POST /memberships/transition with the body', async () => {
    const body = { member_ids: ['M-1', 'M-2'], target: 'lapsed' };
    await bulkTransition(body);
    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${BASE}/memberships/transition`);
    expect(init.body).toBe(JSON.stringify(body));
  });
});

describe('membersApiService — 401 refresh + retry-once (task 16.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('VITE_MEMBERS_API_BASE_URL', BASE);
    global.fetch = vi.fn();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('on 401 rebuilds headers with a refreshed token and retries exactly once', async () => {
    // First buildHeaders sees the stale token; after the 401, buildHeaders is
    // called again and now sees the refreshed token.
    mockGetTokens
      .mockResolvedValueOnce({ idToken: 'stale', accessToken: 'a' } as never)
      .mockResolvedValueOnce({ idToken: 'fresh', accessToken: 'a' } as never);

    vi.mocked(global.fetch)
      .mockResolvedValueOnce(createMockResponse({ ok: false, status: 401 }))
      .mockResolvedValueOnce(createMockResponse({ body: { data: [] } }));

    const rows = await listMembers();

    // Exactly one retry (two fetches total), and the second attempt's result
    // is what the caller receives.
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(rows).toEqual([]);

    // The retry carried the REFRESHED bearer token.
    const retryHeaders = headersOf(fetchCall(1)[1]);
    expect(retryHeaders.Authorization).toBe('Bearer fresh');
    // The first attempt used the stale token.
    expect(headersOf(fetchCall(0)[1]).Authorization).toBe('Bearer stale');
  });

  it('does not retry on a successful first response', async () => {
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'a' } as never);
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({ body: { data: [] } }),
    );

    await listMembers();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('surfaces a non-401 error via handleResponse (throws the server error message)', async () => {
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'a' } as never);
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 400,
        body: { error: 'Invalid scope filter' },
      }),
    );

    await expect(listMembers()).rejects.toThrow('Invalid scope filter');
    // Non-401 => no retry.
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('falls back to error.message when the error body has no `error` field', async () => {
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'a' } as never);
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 500,
        body: { message: 'Internal failure' },
      }),
    );

    await expect(getFieldConfig()).rejects.toThrow('Internal failure');
  });
});
