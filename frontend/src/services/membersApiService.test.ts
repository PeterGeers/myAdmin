/**
 * Members API Service - Unit Tests
 *
 * Focused on the envelope-unwrapping + member-flattening behaviour: the module
 * wraps every 2xx body as `{ data: <result> }` and member records are NESTED
 * (`personal`/`membership`/`scope_values`). The service normalises both so the
 * page's flat-shape reads resolve.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
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
  getColumnPreferences,
  saveColumnPreferences,
} from './membersApiService';
import { createMockResponse } from '@/test-utils/mockHelpers';

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
      // Current member shape (s5d): region is a PLAIN scalar under the `overlay` bucket;
      // personal carries first_name/last_name/email (not the legacy name/contact).
      const enveloped = {
        data: [
          {
            member_id: 'M-1',
            personal: { first_name: 'Jan', last_name: 'Jansen', email: 'm-1@h-dcn.example' },
            membership: {
              member_number: '1001',
              membership_type: 'regulier',
              status: 'active',
            },
            overlay: { region: 'Noord' },
          },
        ],
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: enveloped }),
      );

      const rows = await listMembers();

      // The flat convenience aliases the table's default columns read.
      expect(rows[0]).toMatchObject({
        member_id: 'M-1',
        name: 'Jan Jansen',
        email: 'm-1@h-dcn.example',
        status: 'active',
        membership_type: 'regulier',
        member_number: '1001',
        region: 'Noord',
      });
      // The nested buckets are RETAINED (spread `...rec`) so the nested-first `valueFor`
      // accessor used by the table + modal can resolve overlay/fixed fields.
      expect(rows[0]).toHaveProperty('overlay');
      expect((rows[0] as unknown as { overlay: { region: string } }).overlay.region).toBe('Noord');
    });

    it('derives the flat region alias from overlay.region (s5d shape) — regression', async () => {
      // Regression for the empty-Regio-column bug: flattenMember must read overlay.region
      // (current shape), NOT the retired scope_values.region array. The table's
      // region_display column + the region filter depend on this flat alias.
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: { data: [{ member_id: 'M-R', overlay: { region: 'Utrecht' } }] },
        }),
      );
      const rows = await listMembers();
      expect(rows[0].region).toBe('Utrecht');
    });

    it('falls back to legacy scope_values.region for an old-shaped record', async () => {
      // Back-compat: an old record with no overlay.region still resolves via the legacy array.
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: { data: [{ member_id: 'M-L', scope_values: { region: ['Noord'] } }] },
        }),
      );
      const rows = await listMembers();
      expect(rows[0].region).toBe('Noord');
    });

    it('returns [] when the enveloped data is not an array', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: null } }),
      );
      await expect(listMembers()).resolves.toEqual([]);
    });

    it('leaves region undefined when neither overlay.region nor a legacy value is present', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: { data: [{ member_id: 'M-2', overlay: {}, scope_values: { region: [] } }] },
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
              personal: { first_name: 'Piet', email: 'piet@h-dcn.example' },
              membership: { membership_type: 'student', status: 'pending' },
              overlay: { region: 'Zuid' },
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

// ============================================================================
// Task 2.5.5 — column-preferences client wrappers (Session Columns, R6)
//
// A 1:1 mirror of the preferred-list wrappers (`columns` ↔ `refs`). We assert
// the same seam behaviour as the sibling suites: the `{ data }` envelope is
// unwrapped, `columns` is coerced to a clean `string[]` (non-string/empty
// dropped), an unset list defaults to `[]`, and the PUT sends a `{ columns }`
// body to the LITERAL `/members/column-preferences` path (matching the
// server-side routes declared in task 2.5.4).
// ============================================================================

describe('membersApiService — column preferences (task 2.5.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('VITE_MEMBERS_API_BASE_URL', BASE);
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'acc' } as never);
    global.fetch = vi.fn();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  describe('getColumnPreferences', () => {
    // Validates: Requirements 6.1
    it('unwraps the {data} envelope and maps { sub, columns, updated_at }', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: {
            data: {
              sub: 'user-sub-1',
              columns: ['years_member', 'region', 'status'],
              updated_at: '2026-01-02T03:04:05Z',
            },
          },
        }),
      );

      await expect(getColumnPreferences()).resolves.toEqual({
        sub: 'user-sub-1',
        columns: ['years_member', 'region', 'status'],
        updated_at: '2026-01-02T03:04:05Z',
      });
    });

    // Validates: Requirements 4.5, 5.2
    it('GET /members/column-preferences (literal path, no path param)', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: { columns: [] } } }),
      );
      await getColumnPreferences();
      const [url, init] = fetchCall();
      expect(init.method).toBe('GET');
      expect(url).toBe(`${BASE}/members/column-preferences`);
    });

    // Validates: Requirements 6.6
    it('drops non-string / empty entries from columns', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: {
            data: {
              sub: 'user-sub-1',
              columns: ['years_member', '', 42, null, 'region', undefined],
              updated_at: '2026-01-02T03:04:05Z',
            },
          },
        }),
      );

      const prefs = await getColumnPreferences();
      expect(prefs.columns).toEqual(['years_member', 'region']);
    });

    // Validates: Requirements 6.4
    it('defaults to empty columns when the list is unset', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: { sub: 'user-sub-1', columns: [] } } }),
      );
      const prefs = await getColumnPreferences();
      expect(prefs.columns).toEqual([]);
      expect(prefs.sub).toBe('user-sub-1');
      expect(prefs.updated_at).toBe('');
    });

    // Validates: Requirements 6.4
    it('defaults columns to [] when the backend omits the field entirely', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: {} } }),
      );
      const prefs = await getColumnPreferences();
      expect(prefs).toEqual({ sub: '', columns: [], updated_at: '' });
    });
  });

  describe('saveColumnPreferences', () => {
    // Validates: Requirements 4.5, 5.2
    it('PUT /members/column-preferences with a { columns } body', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: {
            data: {
              sub: 'user-sub-1',
              columns: ['years_member', 'region'],
              updated_at: '2026-02-02T00:00:00Z',
            },
          },
        }),
      );

      const result = await saveColumnPreferences(['years_member', 'region']);

      const [url, init] = fetchCall();
      expect(init.method).toBe('PUT');
      expect(url).toBe(`${BASE}/members/column-preferences`);
      expect(init.body).toBe(JSON.stringify({ columns: ['years_member', 'region'] }));
      // The reply is unwrapped + mapped the same way as the GET.
      expect(result).toEqual({
        sub: 'user-sub-1',
        columns: ['years_member', 'region'],
        updated_at: '2026-02-02T00:00:00Z',
      });
    });

    // Validates: Requirements 6.4
    it('sends an empty { columns: [] } body to clear the list', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: { sub: 'user-sub-1', columns: [] } } }),
      );
      await saveColumnPreferences([]);
      const [, init] = fetchCall();
      expect(init.body).toBe(JSON.stringify({ columns: [] }));
    });
  });

  // ==========================================================================
  // Task 3.4 — the dedicated delivery route (PUT/DELETE), R3, design §3.
  //
  // The create/update set bodies deliberately do NOT carry delivery; the stored
  // delivery is written/cleared ONLY via `/members/analytics-sets/{id}/delivery`.
  // `putAnalyticsSetDelivery` maps the camelCase MemberDelivery to the stored
  // snake_case block (via deliveryToBackend) and PUTs it; `deleteAnalyticsSetDelivery`
  // DELETEs the same path.
  // ==========================================================================
  describe('analytics-set delivery route (task 3.4)', () => {
    // Validates: Requirements 3 (R3)
    it('PUT /delivery maps the body via deliveryToBackend and returns the mapped set', async () => {
      const { putAnalyticsSetDelivery } = await import('./membersApiService');
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({
          body: {
            data: {
              set_id: 'set-1',
              name: 'Jubilees',
              kind: 'list',
              definition: {},
              delivery: {
                mode: 'to_fixed',
                template_id: null,
                attachment: 'csv',
                recipients: ['agent@example.com'],
                label_options: null,
              },
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-02T00:00:00Z',
            },
          },
        }),
      );

      const result = await putAnalyticsSetDelivery('set-1', {
        mode: 'to_fixed',
        templateId: null,
        attachment: 'csv',
        recipients: ['agent@example.com'],
        labelOptions: null,
      });

      const [url, init] = fetchCall();
      expect(init.method).toBe('PUT');
      expect(url).toBe(`${BASE}/members/analytics-sets/set-1/delivery`);
      // The body IS the bare snake_case delivery block — NOT wrapped in
      // `{ delivery: ... }`. The backend reads the request body directly as the
      // block (`_write_body(request)`); a wrapper makes `mode` absent → 422.
      expect(JSON.parse(init.body as string)).toEqual({
        mode: 'to_fixed',
        template_id: null,
        attachment: 'csv',
        recipients: ['agent@example.com'],
        label_options: null,
      });
      // The reply is unwrapped + mapped back to the camelCase set (with delivery).
      expect(result.id).toBe('set-1');
      expect(result.delivery).toEqual({
        mode: 'to_fixed',
        templateId: null,
        attachment: 'csv',
        recipients: ['agent@example.com'],
        labelOptions: null,
      });
    });

    // Validates: Requirements 3 (R3)
    it('DELETE /delivery targets the dedicated delivery path', async () => {
      const { deleteAnalyticsSetDelivery } = await import('./membersApiService');
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ body: { data: { ok: true } } }),
      );

      await deleteAnalyticsSetDelivery('set-1');

      const [url, init] = fetchCall();
      expect(init.method).toBe('DELETE');
      expect(url).toBe(`${BASE}/members/analytics-sets/set-1/delivery`);
    });
  });
});

// ============================================================================
// Task 3.2 — delivery block mappers (R3, design §2.1)
//
// `deliveryToBackend` / `deliveryFromBackend` are the frontend ↔ backend set
// mappers' delivery half: they convert the camelCase `MemberDelivery` to/from the
// stored snake_case block (`{ mode, template_id, attachment, recipients,
// label_options }`), using the shared label-options model's `toStored`/`fromStored`
// for the `label_options` sub-block (one label-options model with R6 — task 6.3).
// These tests round-trip BOTH modes so the camelCase ↔ snake_case mapping (incl.
// the numeric label_options) is proven lossless.
// ============================================================================

describe('membersApiService — delivery block mappers (task 3.2)', () => {
  // Validates: Requirements 3 (R3)
  it('round-trips a per_recipient delivery (template, no recipients, no labels)', async () => {
    const { deliveryToBackend, deliveryFromBackend } = await import('./membersApiService');

    const delivery = {
      mode: 'per_recipient' as const,
      templateId: 'template#t-1',
      attachment: 'csv' as const,
      recipients: [],
      labelOptions: null,
    };

    const stored = deliveryToBackend(delivery);
    // per_recipient stores NO recipient addresses (resolved from the dataset at run time).
    expect(stored.mode).toBe('per_recipient');
    expect(stored.template_id).toBe('template#t-1');
    expect(stored.attachment).toBe('csv');
    expect(stored.recipients).toEqual([]);
    expect(stored.label_options).toBeNull();

    // Rebuild from the stored block → the original camelCase shape.
    expect(deliveryFromBackend(stored)).toEqual(delivery);
  });

  // Validates: Requirements 3 (R3)
  it('round-trips a to_fixed delivery with pdf_labels (numeric label_options survive)', async () => {
    const { deliveryToBackend, deliveryFromBackend } = await import('./membersApiService');
    const { normalizeLabelOptions } = await import(
      '../components/members/analytics/labelOptions'
    );

    const labelOptions = normalizeLabelOptions({
      format: 'L7160',
      sortOrder: 'postcode',
      fontSize: 11,
      alignment: 'center',
      showBorder: true,
      showCountry: false,
      startPosition: 4,
    });
    const delivery = {
      mode: 'to_fixed' as const,
      templateId: null,
      attachment: 'pdf_labels' as const,
      recipients: ['agent@example.com', 'back@example.com'],
      labelOptions,
    };

    const stored = deliveryToBackend(delivery);
    expect(stored.mode).toBe('to_fixed');
    expect(stored.recipients).toEqual(['agent@example.com', 'back@example.com']);
    // label_options serialized to the snake_case stored block with numeric fields intact.
    expect(stored.label_options).toEqual({
      format: 'L7160',
      sort: 'postcode',
      font_size: 11,
      alignment: 'center',
      border: true,
      country: false,
      start: 4,
    });

    // Full round-trip rebuilds the camelCase delivery (labelOptions normalized identically).
    expect(deliveryFromBackend(stored)).toEqual(delivery);
  });

  // Validates: Requirements 3 (R3)
  it('maps an absent / null stored block to undefined (a set with no delivery)', async () => {
    const { deliveryFromBackend } = await import('./membersApiService');
    expect(deliveryFromBackend(null)).toBeUndefined();
    expect(deliveryFromBackend(undefined)).toBeUndefined();
  });

  // Validates: Requirements 3 (R3)
  it('a to_fixed non-pdf_labels delivery carries no label_options', async () => {
    const { deliveryToBackend, deliveryFromBackend } = await import('./membersApiService');

    const delivery = {
      mode: 'to_fixed' as const,
      templateId: null,
      attachment: 'csv' as const,
      recipients: ['agent@example.com'],
      labelOptions: null,
    };

    const stored = deliveryToBackend(delivery);
    expect(stored.label_options).toBeNull();
    expect(deliveryFromBackend(stored)).toEqual(delivery);
  });
});

// ============================================================================
// Task 5.4 — schedule route + cadence↔cron mapping (R5, design §2.3/§3/§5)
//
// `GET/POST/PUT/DELETE /members/schedules[/{id}]`. A schedule carries
// `{ schedule_id, set_id, cron, enabled, created_by, created_at, updated_at }`.
// The UI edits a FRIENDLY cadence (monthly/weekly) which maps to a concrete cron
// via `cadenceToCron`; an existing schedule's cron maps back via `cronToCadence`.
// ============================================================================

describe('membersApiService — schedules (task 5.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('VITE_MEMBERS_API_BASE_URL', 'http://members.test/api');
    mockGetTokens.mockResolvedValue({ idToken: 'tok', accessToken: 'acc' } as never);
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  const SBASE = 'http://members.test/api';

  // Validates: Requirements 5 (R5)
  it('cadenceToCron maps each friendly cadence to its backend cron (design §5)', async () => {
    const { cadenceToCron, CADENCE_CRON } = await import('./membersApiService');
    expect(cadenceToCron('monthly')).toBe('cron(0 8 1 * ? *)');
    expect(cadenceToCron('weekly')).toBe('cron(0 8 ? * MON *)');
    // The forward map is the single source of truth.
    expect(cadenceToCron('monthly')).toBe(CADENCE_CRON.monthly);
    expect(cadenceToCron('weekly')).toBe(CADENCE_CRON.weekly);
  });

  // Validates: Requirements 5 (R5)
  it('cronToCadence recovers the cadence, falling back to monthly for an unknown cron', async () => {
    const { cronToCadence } = await import('./membersApiService');
    expect(cronToCadence('cron(0 8 1 * ? *)')).toBe('monthly');
    expect(cronToCadence('cron(0 8 ? * MON *)')).toBe('weekly');
    // Round-trip stability.
    expect(cronToCadence('cron(0 8 1 * ? *)')).toBe('monthly');
    // An unrecognized expression → monthly (the editor still opens).
    expect(cronToCadence('rate(13 hours)')).toBe('monthly');
    expect(cronToCadence('')).toBe('monthly');
  });

  // Validates: Requirements 5 (R5)
  it('listSchedulesForSet GETs /members/schedules and returns only the set\'s schedules', async () => {
    const { listSchedulesForSet } = await import('./membersApiService');
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        body: {
          data: [
            {
              schedule_id: 'sch-1',
              set_id: 'set-1',
              cron: 'cron(0 8 1 * ? *)',
              enabled: true,
              created_by: 'sub-1',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
            { schedule_id: 'sch-2', set_id: 'OTHER', cron: 'cron(0 8 ? * MON *)', enabled: false },
          ],
        },
      }),
    );

    const result = await listSchedulesForSet('set-1');

    const [url, init] = fetchCall();
    expect(init.method).toBe('GET');
    expect(url).toBe(`${SBASE}/members/schedules`);
    // Only the schedules for set-1 survive the filter, mapped to camelCase.
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      scheduleId: 'sch-1',
      setId: 'set-1',
      cron: 'cron(0 8 1 * ? *)',
      enabled: true,
      createdBy: 'sub-1',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    });
  });

  // Validates: Requirements 5 (R5)
  it('createSchedule POSTs /members/schedules with the mapped cron (no tenant/created_by in body)', async () => {
    const { createSchedule } = await import('./membersApiService');
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        body: {
          data: {
            schedule_id: 'sch-1',
            set_id: 'set-1',
            cron: 'cron(0 8 1 * ? *)',
            enabled: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        },
      }),
    );

    const result = await createSchedule('set-1', 'monthly', true);

    const [url, init] = fetchCall();
    expect(init.method).toBe('POST');
    expect(url).toBe(`${SBASE}/members/schedules`);
    // Body carries only domain fields; the cadence is mapped to a cron.
    expect(JSON.parse(init.body as string)).toEqual({
      set_id: 'set-1',
      cron: 'cron(0 8 1 * ? *)',
      enabled: true,
    });
    expect(result.scheduleId).toBe('sch-1');
    expect(result.enabled).toBe(true);
  });

  // Validates: Requirements 5 (R5)
  it('updateSchedule PUTs /members/schedules/{id} with the mapped cron + enabled toggle', async () => {
    const { updateSchedule } = await import('./membersApiService');
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        body: {
          data: {
            schedule_id: 'sch-1',
            set_id: 'set-1',
            cron: 'cron(0 8 ? * MON *)',
            enabled: false,
          },
        },
      }),
    );

    const result = await updateSchedule('sch-1', 'weekly', false);

    const [url, init] = fetchCall();
    expect(init.method).toBe('PUT');
    expect(url).toBe(`${SBASE}/members/schedules/sch-1`);
    expect(JSON.parse(init.body as string)).toEqual({
      cron: 'cron(0 8 ? * MON *)',
      enabled: false,
    });
    // The disabled toggle round-trips.
    expect(result.enabled).toBe(false);
  });

  // Validates: Requirements 5 (R5)
  it('deleteSchedule DELETEs /members/schedules/{id} (id url-encoded)', async () => {
    const { deleteSchedule } = await import('./membersApiService');
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({ body: { data: { ok: true } } }),
    );

    await deleteSchedule('sch/9');

    const [url, init] = fetchCall();
    expect(init.method).toBe('DELETE');
    expect(url).toBe(`${SBASE}/members/schedules/sch%2F9`);
  });

  // Validates: Requirements 5 (R5)
  it('listAnalyticsSets surfaces hasDelivery so the UI can gate the Schedule action', async () => {
    const { listAnalyticsSets } = await import('./membersApiService');
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        body: {
          data: [
            {
              set_id: 'with-delivery',
              name: 'Has delivery',
              kind: 'list',
              definition: {},
              delivery: {
                mode: 'to_fixed',
                template_id: null,
                attachment: 'csv',
                recipients: ['a@b.com'],
                label_options: null,
              },
            },
            { set_id: 'no-delivery', name: 'Bare', kind: 'count', definition: {} },
          ],
        },
      }),
    );

    const sets = await listAnalyticsSets();
    expect(sets.find((s) => s.id === 'with-delivery')?.hasDelivery).toBe(true);
    expect(sets.find((s) => s.id === 'no-delivery')?.hasDelivery).toBe(false);
  });
});
