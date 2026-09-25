/**
 * Members Module API Service
 *
 * The single frontend seam reaching the Members module API (component C7).
 *
 * IMPORTANT: The Members module is a SEPARATE SAM app, NOT the Flask backend.
 * All requests therefore target `MEMBERS_API_BASE_URL` (from
 * `import.meta.env.VITE_MEMBERS_API_BASE_URL`) instead of the Flask
 * `API_BASE_URL` used by `apiService.ts`.
 *
 * Header semantics mirror `frontend/src/services/apiService.ts` exactly:
 *   - `Authorization: Bearer <Cognito ID token>` via `getCurrentAuthTokens()`
 *   - `X-Tenant`   from `localStorage['selectedTenant']` (or a per-call override)
 *   - `X-Language` from `localStorage['i18nextLng']` (default `nl`)
 *   - a single 401 -> refresh-token -> retry-once path
 *
 * The Members API is authenticated purely by the Bearer token — it does NOT
 * use cookies, so requests are sent WITHOUT `credentials: 'include'` (that
 * option was removed earlier; do not re-add it).
 *
 * Response envelope: the module wraps every 2xx body as `{ "data": <result> }`.
 * The wrappers below unwrap that envelope (see `unwrapData`) so callers receive
 * the payload, not the envelope, and `listMembers`/`getMember` additionally
 * flatten the nested member record (see `flattenMember`) to the flat `Member`
 * shape the page/types expect.
 *
 * Verified-token flow (ADR 0004, R7.4): the SPA sends the Cognito ID token as a
 * bearer token; the module edge authenticates via `get_verified_claims` and
 * derives the tenant from the verified entitlement. `X-Tenant`/`X-Language` are
 * sent purely as context (they grant nothing), exactly as `apiService.ts` does.
 *
 * Response handling mirrors `sysadminService.ts` (`handleResponse`): non-2xx
 * throws an Error carrying the server's `error`/`message`; 2xx returns parsed
 * JSON.
 *
 * Types are intentionally minimal here (generic `T` defaults + `unknown` bodies)
 * — task 16.2 adds `frontend/src/types/members.ts` and can refine these
 * signatures without changing the request plumbing.
 *
 * _Requirements: R7.3, R7.4_
 */

import { getCurrentAuthTokens } from './authService';
import { apiErrorFromResponse } from '../shared/api/ApiError';
import type { Member } from '../types/members';

// ============================================================================
// Fail-fast base URL resolution (R7.3)
// ============================================================================

/**
 * Resolve the Members module API base URL, failing fast when it is unset/blank.
 *
 * The value comes from `import.meta.env.VITE_MEMBERS_API_BASE_URL` (task 1.3
 * established the `VITE_` prefix + `frontend/.env.local` / `.env.example`). We
 * resolve lazily (on first request) rather than at module load so that the
 * failure is testable and does not break unrelated imports, but the effect is
 * the same fail-fast contract: no silent fallback to a wrong/relative base.
 *
 * @returns The trimmed, trailing-slash-free base URL.
 * @throws Error if the env var is unset or blank.
 */
function getMembersApiBaseUrl(): string {
  const raw = import.meta.env.VITE_MEMBERS_API_BASE_URL as string | undefined;
  const base = (raw ?? '').trim();
  if (!base) {
    throw new Error(
      'VITE_MEMBERS_API_BASE_URL is not set. The Members module API base URL ' +
      'must be configured (see frontend/.env.local / .env.example).'
    );
  }
  // Normalise a single trailing slash away so `${base}${endpoint}` stays clean.
  return base.replace(/\/+$/, '');
}

// ============================================================================
// Request plumbing (mirrors apiService.ts authenticatedRequest)
// ============================================================================

/**
 * Options for a Members module request. Mirrors the subset of
 * `AuthenticatedRequestOptions` that the Members seam needs.
 */
export interface MembersRequestOptions extends RequestInit {
  /** Optional tenant override (defaults to `localStorage['selectedTenant']`). */
  tenant?: string;
}

/** Read the current tenant from localStorage (matches apiService.ts). */
function getCurrentTenant(): string | null {
  try {
    return localStorage.getItem('selectedTenant');
  } catch {
    return null;
  }
}

/** Read the current UI language from localStorage (matches apiService.ts). */
function getCurrentLanguage(): string {
  try {
    return localStorage.getItem('i18nextLng') || 'nl';
  } catch {
    return 'nl';
  }
}

/**
 * Build the authenticated header set (Authorization + X-Tenant + X-Language).
 * Extracted so the initial request and the post-refresh retry stay identical.
 */
async function buildHeaders(
  base: HeadersInit,
  tenant?: string
): Promise<HeadersInit> {
  const tokens = await getCurrentAuthTokens();
  if (!tokens?.idToken) {
    throw new Error('No authentication token available');
  }

  let headers: HeadersInit = {
    ...base,
    'X-Language': getCurrentLanguage(),
    Authorization: `Bearer ${tokens.idToken}`,
  };

  const currentTenant = tenant || getCurrentTenant();
  if (currentTenant) {
    headers = { ...headers, 'X-Tenant': currentTenant };
  }

  return headers;
}

/**
 * Make an authenticated request against the Members module API.
 *
 * Mirrors `apiService.ts::authenticatedRequest`: JWT bearer auth, `X-Tenant` +
 * `X-Language` context headers, and a single 401 -> refresh -> retry-once
 * path. The Members API is Bearer-token only (no cookies), so no
 * `credentials: 'include'`. Differs from Flask only in the base URL
 * (`MEMBERS_API_BASE_URL`).
 *
 * @param endpoint - Path beginning with `/` (e.g. `/members`).
 * @param options  - Fetch options with an optional `tenant` override.
 * @returns The raw `Response` (callers use `handleResponse` to parse).
 */
export async function membersRequest(
  endpoint: string,
  options: MembersRequestOptions = {}
): Promise<Response> {
  const { tenant, ...fetchOptions } = options;
  const url = `${getMembersApiBaseUrl()}${endpoint}`;

  const baseHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    ...fetchOptions.headers,
  };

  let headers: HeadersInit;
  try {
    headers = await buildHeaders(baseHeaders, tenant);
  } catch (error) {
    console.error('Failed to get authentication tokens:', error);
    throw new Error('Authentication required');
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // 401 -> refresh token -> retry once (matches apiService.ts).
  if (response.status === 401) {
    console.warn('Received 401 Unauthorized from Members API - token may be expired');
    try {
      const retryHeaders = await buildHeaders(baseHeaders, tenant);
      return await fetch(url, {
        ...fetchOptions,
        headers: retryHeaders,
      });
    } catch (refreshError) {
      console.error('Failed to refresh token:', refreshError);
      throw new Error('Session expired - please log in again');
    }
  }

  return response;
}

/**
 * Parse a Members API response, throwing on non-2xx.
 *
 * On `!response.ok` throws a structured {@link ApiError} (API response & error standard v1.0)
 * that preserves the whole envelope — `status`, the machine `code`, `params`, the RFC 9457
 * per-field `errors[]` and `reasons[]` arrays — so `applyApiError` can surface localized inline
 * field errors + a summary toast. Backward compatible: `ApiError extends Error`, so a legacy
 * `catch (e) { toast(e.message) }` still reads the backend English `error` (or `HTTP <status>`).
 * A non-JSON/empty error body degrades to `HTTP <status>` via `apiErrorFromResponse`.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

// Thin method helpers so wrappers read cleanly.
async function getJson<T>(endpoint: string, options: MembersRequestOptions = {}): Promise<T> {
  return handleResponse<T>(await membersRequest(endpoint, { ...options, method: 'GET' }));
}

async function postJson<T>(
  endpoint: string,
  body?: unknown,
  options: MembersRequestOptions = {}
): Promise<T> {
  return handleResponse<T>(
    await membersRequest(endpoint, {
      ...options,
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  );
}

async function putJson<T>(
  endpoint: string,
  body?: unknown,
  options: MembersRequestOptions = {}
): Promise<T> {
  return handleResponse<T>(
    await membersRequest(endpoint, {
      ...options,
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  );
}

async function deleteJson<T>(endpoint: string, options: MembersRequestOptions = {}): Promise<T> {
  return handleResponse<T>(await membersRequest(endpoint, { ...options, method: 'DELETE' }));
}

// ============================================================================
// Envelope unwrapping + member flattening
//
// The Members module wraps EVERY 2xx body as `{ "data": <result> }` (see the
// SAM handler `_response`/`handler`). Member records are also NESTED, not flat.
// These helpers normalise both so the page/types keep their flat-shape reads.
// ============================================================================

/**
 * Unwrap the module's `{ data: <result> }` envelope.
 *
 * Returns `payload.data` when the parsed response is a non-null object carrying
 * a `data` property; otherwise returns the payload as-is (so a future
 * non-enveloped response still works). Defensive by design — never throws.
 *
 * @param payload - The parsed JSON body (envelope or bare payload).
 * @returns The unwrapped payload, typed as `T`.
 */
function unwrapData<T>(payload: unknown): T {
  if (
    payload !== null &&
    typeof payload === 'object' &&
    'data' in (payload as Record<string, unknown>)
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

/**
 * The `personal` bucket of a nested member record. The module stores fixed
 * personal fields under their REAL keys (`first_name`/`last_name`/`email`/...),
 * not the legacy `name`/`contact` aliases. `display_name`/`name_infix` are
 * optional convenience/derived keys used to build the table's `name` column.
 */
interface NestedPersonal {
  display_name?: string;
  first_name?: string;
  name_infix?: string;
  last_name?: string;
  email?: string;
  [key: string]: unknown;
}

/** The nested member record shape as returned by the module (pre-flatten). */
interface NestedMemberRecord {
  member_id?: string;
  personal?: NestedPersonal | null;
  membership?: {
    membership_id?: string;
    member_number?: string;
    membership_type?: string;
    status?: string;
  } | null;
  //: The tenant OVERLAY bucket — where region now lives as a plain scalar
  //: (`overlay.region`) since s5d retired the `scope_values` bucket.
  overlay?: Record<string, unknown> | null;
  //: LEGACY (retired s5d) — kept only as a fallback so an old-shaped record still resolves.
  scope_values?: { region?: string[] } | null;
  [key: string]: unknown;
}

/**
 * Build the `name` display value from the REAL personal shape.
 *
 * Prefers an explicit `display_name`; else joins `first_name`/`name_infix`/
 * `last_name` (dropping blanks); else falls back to whichever single name part
 * is present. Returns `undefined` when nothing is available so callers/render
 * fall through to the placeholder dash.
 */
function personalDisplayName(personal: NestedPersonal | null | undefined): string | undefined {
  if (!personal) return undefined;
  if (personal.display_name) return personal.display_name;
  const joined = [personal.first_name, personal.name_infix, personal.last_name]
    .filter(Boolean)
    .join(' ')
    .trim();
  if (joined) return joined;
  return personal.first_name || personal.last_name || undefined;
}

/**
 * Normalise a member record to the `Member` shape the page/types read, WITHOUT
 * discarding the nested storage buckets.
 *
 * The bug this fixes: the previous implementation DESTRUCTURED OUT
 * `personal`/`membership`/`scope_values`, so the returned object no longer
 * carried those buckets — and the shared `valueFor(member, group, key)`
 * accessor (used by the view modal AND the overview table cells) reads
 * `member[group][key]` first, then falls back to `member[key]`. With the
 * buckets gone AND no flat aliases for the fixed personal/membership fields
 * (first_name, last_name, birth_date, street, joined_date, ...), every fixed
 * field resolved to nothing → a dash. Only `overlay`/top-level scalars (which
 * rode along in `...rest`) displayed.
 *
 * The fix: spread the WHOLE record (`...rec`) so `personal`/`membership`/
 * `overlay`/`scope_values` survive intact for the nested-first accessor, then
 * layer the flat CONVENIENCE keys the default table columns read
 * (`name`/`email`/`status`/`membership_type`/`member_number`/`membership_id`/
 * `region`) ON TOP — now mapped to the REAL nested shape.
 *
 * @param raw - The (possibly nested) member record from the API.
 * @returns The normalised `Member` (nested buckets retained + flat aliases).
 */
function flattenMember(raw: unknown): Member {
  const rec = (raw ?? {}) as NestedMemberRecord;
  const { personal, membership, overlay, scope_values } = rec;

  // Region is a PLAIN overlay scalar since s5d (`member.overlay.region`); the old
  // `scope_values.region` ARRAY bucket was retired. Read overlay first (the current shape),
  // fall back to the legacy array only for an old-shaped record. This flat alias is what the
  // table's `region_display` column + the region filter depend on (the modal reads the nested
  // `overlay.region` directly via `valueFor`, which is why the modal was never affected).
  const overlayRegion = overlay && typeof overlay === 'object' ? overlay.region : undefined;
  const legacyRegion = Array.isArray(scope_values?.region) ? scope_values?.region[0] : undefined;
  const region =
    typeof overlayRegion === 'string' && overlayRegion ? overlayRegion : legacyRegion;

  return {
    // Retain the nested buckets (personal/membership/overlay/scope_values) AND
    // any top-level scalars/overlay fields so the nested-or-flat `valueFor`
    // accessor can resolve fixed fields (personal.first_name, ...) and overlay
    // fields alike.
    ...rec,
    member_id: rec.member_id ?? '',
    // Convenience flat aliases for the table's default columns — mapped to the
    // REAL nested shape (personal.email, a composed display name), not the
    // stale personal.name/personal.contact keys that never existed.
    name: personalDisplayName(personal),
    email: personal?.email,
    status: membership?.status,
    membership_type: membership?.membership_type,
    member_number: membership?.member_number,
    // Surface the primary membership id (when the module returns one on the
    // nested `membership` object) so the single-transition action can target it
    // (POST /members/{id}/memberships/{membership_id}/transition). A top-level
    // `membership_id` on the record still wins if present.
    membership_id: rec.membership_id ?? membership?.membership_id,
    region,
  } as Member;
}

// ============================================================================
// Typed route wrappers (component C7 + module API contract C13)
//
// Every wrapper unwraps the `{ data: ... }` envelope so callers get the payload,
// not the envelope. `listMembers`/`getMember` additionally flatten member
// records to the flat `Member` shape; `getFieldConfig` unwraps the enveloped
// field config. The remaining wrappers keep their generic `<T>` signatures.
// ============================================================================

/**
 * GET /members — list members visible in the caller's allowed scopes.
 *
 * Unwraps the `{ data: [...] }` envelope, ensures the result is an array, and
 * flattens each nested member record to the flat `Member` shape. Returns a
 * `Member[]` regardless of the caller's generic `T` so the page's
 * `Array.isArray` check and flat field reads always resolve.
 */
export async function listMembers<T = Member[]>(): Promise<T> {
  const payload = await getJson<unknown>('/members');
  const rows = unwrapData<unknown>(payload);
  const list = Array.isArray(rows) ? rows : [];
  return list.map(flattenMember) as unknown as T;
}

/** POST /members/search — filtered member search. */
export async function searchMembers<T = unknown>(filters: unknown): Promise<T> {
  return unwrapData<T>(await postJson<unknown>('/members/search', filters));
}

/**
 * GET /members/{member_id} — a single member.
 *
 * Unwraps the `{ data: {...} }` envelope and flattens the nested record.
 */
export async function getMember<T = Member>(memberId: string): Promise<T> {
  const payload = await getJson<unknown>(`/members/${encodeURIComponent(memberId)}`);
  const record = unwrapData<unknown>(payload);
  return flattenMember(record) as unknown as T;
}

/** POST /members — create a member. */
export async function createMember<T = unknown>(body: unknown): Promise<T> {
  return unwrapData<T>(await postJson<unknown>('/members', body));
}

/** PUT /members/{member_id} — update a member. */
export async function updateMember<T = unknown>(memberId: string, body: unknown): Promise<T> {
  return unwrapData<T>(await putJson<unknown>(`/members/${encodeURIComponent(memberId)}`, body));
}

/** DELETE /members/{member_id} — delete a member. */
export async function deleteMember<T = unknown>(memberId: string): Promise<T> {
  return unwrapData<T>(await deleteJson<unknown>(`/members/${encodeURIComponent(memberId)}`));
}

/**
 * GET /members/export — export the caller's members (scope-narrowed server-side).
 *
 * The `export_members` module action is AUTHORITATIVE for scope + resolved
 * fields: it returns the same list-of-records shape as `GET /members`, already
 * narrowed to the caller's scope server-side (R5.6, R8.7 — the SPA never invents
 * scope). We unwrap the `{ data: [...] }` envelope and flatten each nested
 * record to the flat `Member` shape (exactly like `listMembers`) so callers can
 * serialize the resolved flat + overlay keys straight to CSV. Returns a
 * `Member[]` regardless of the caller's generic `T`.
 */
export async function exportMembers<T = Member[]>(): Promise<T> {
  const payload = await getJson<unknown>('/members/export');
  const rows = unwrapData<unknown>(payload);
  const list = Array.isArray(rows) ? rows : [];
  return list.map(flattenMember) as unknown as T;
}

/** GET /members/field-config — the resolved field configuration/overlay. */
export async function getFieldConfig<T = unknown>(): Promise<T> {
  return unwrapData<T>(await getJson<unknown>('/members/field-config'));
}

/**
 * GET /membership-types — the membership-type catalog.
 * @param activeOnly - when true, appends `?active_only=true`.
 */
export async function listMembershipTypes<T = unknown>(activeOnly?: boolean): Promise<T> {
  const endpoint = activeOnly ? '/membership-types?active_only=true' : '/membership-types';
  return unwrapData<T>(await getJson<unknown>(endpoint));
}

/** POST /members/{member_id}/memberships — create a membership for a member. */
export async function createMembership<T = unknown>(memberId: string, body: unknown): Promise<T> {
  return unwrapData<T>(
    await postJson<unknown>(`/members/${encodeURIComponent(memberId)}/memberships`, body)
  );
}

/**
 * POST /members/{member_id}/memberships/{membership_id}/transition —
 * transition a single membership's state.
 */
export async function transitionMembership<T = unknown>(
  memberId: string,
  membershipId: string,
  body: unknown
): Promise<T> {
  return unwrapData<T>(
    await postJson<unknown>(
      `/members/${encodeURIComponent(memberId)}/memberships/${encodeURIComponent(
        membershipId
      )}/transition`,
      body
    )
  );
}

/** POST /memberships/transition — bulk transition over multiple memberships. */
export async function bulkTransition<T = unknown>(body: unknown): Promise<T> {
  return unwrapData<T>(await postJson<unknown>('/memberships/transition', body));
}
