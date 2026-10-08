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

import { apiErrorFromResponse } from '../shared/api/ApiError';
import {
  fromStored as labelOptionsFromStored,
  toStored as labelOptionsToStored,
} from '../components/members/analytics/labelOptions';
import type { StoredLabelOptions } from '../components/members/analytics/labelOptions';
import type {
  Member,
  MemberAnalyticsSet,
  MemberAnalyticsSetSummary,
  MemberDelivery,
  MemberPreferredList,
  MemberColumnPreferences,
  MemberSchedule,
  MemberScheduleCadence,
} from '../types/members';
import type { PivotConfig } from '../types/pivot';
import { getCurrentAuthTokens } from './authService';
import { fromBackendConfig, toBackendConfig } from './pivotService';

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

// ============================================================================
// Member analytics-sets (saved pivot/list definitions, F-012)
//
// The Members module OWNS member saved-sets in DynamoDB now, replacing the Flask
// `/api/pivot/models` (MySQL) store for the member saved-set path (F-012). These
// wrappers unwrap the `{ data }` envelope and convert the backend snake_case
// `definition` <-> the camelCase `PivotConfig` via `toBackendConfig` /
// `fromBackendConfig` (reused from `pivotService`). The backend `set_id` is a
// STRING (server-chosen uuid4 hex), mapped to the summary/full shape's `id`.
// ============================================================================

/**
 * The raw backend `delivery` block (R3, design §2.1) — the snake_case STORED/wire
 * form the SAM entity persists: `{ mode, template_id, attachment, recipients,
 * label_options }`. `label_options` is the shared snake_case {@link StoredLabelOptions}
 * (one label-options model with R6 — task 6.3). Absent/`null` on a set with no
 * delivery (a legacy set).
 */
interface RawDelivery {
  mode: 'per_recipient' | 'to_fixed';
  template_id?: string | null;
  attachment?: 'csv' | 'pdf_labels' | null;
  recipients?: string[] | null;
  label_options?: Partial<StoredLabelOptions> | null;
}

/** The raw backend analytics-set shape (snake_case `definition`, string `set_id`). */
interface RawAnalyticsSet {
  set_id: string;
  name: string;
  kind: 'count' | 'list';
  definition: Record<string, unknown>;
  delivery?: RawDelivery | null;
  created_at: string;
  updated_at: string;
}

/**
 * Map a stored (snake_case) `delivery` block to the camelCase {@link MemberDelivery},
 * the frontend ↔ backend set mapper's delivery half (R3, design §2.1). Returns
 * `undefined` for an absent/`null` block (a set with no delivery) so the field is
 * simply omitted on the resolved set.
 *
 * The `label_options` sub-block is loaded via the shared model's
 * {@link labelOptionsFromStored} — the SAME label-options model R6 uses, never a
 * fork (task 6.3). It is carried only when the attachment is `pdf_labels`.
 */
export function deliveryFromBackend(raw?: RawDelivery | null): MemberDelivery | undefined {
  if (!raw || (raw.mode !== 'per_recipient' && raw.mode !== 'to_fixed')) {
    return undefined;
  }
  const attachment = raw.attachment ?? null;
  return {
    mode: raw.mode,
    templateId: raw.template_id ?? null,
    attachment,
    recipients: Array.isArray(raw.recipients) ? raw.recipients : [],
    labelOptions:
      attachment === 'pdf_labels'
        ? labelOptionsFromStored(raw.label_options ?? null)
        : null,
  };
}

/**
 * Map a camelCase {@link MemberDelivery} to the stored (snake_case) `delivery`
 * block the backend persists (R3, design §2.1) — the inverse of
 * {@link deliveryFromBackend}, used when writing a set's delivery (task 3.3/3.4).
 *
 * `per_recipient` stores NO recipients (addresses resolve from the dataset at run
 * time — design §2.1); `to_fixed` stores the explicit list. `label_options` is
 * emitted (via the shared model's {@link labelOptionsToStored}) only for the
 * `pdf_labels` attachment, `null` otherwise.
 */
export function deliveryToBackend(delivery: MemberDelivery): RawDelivery {
  return {
    mode: delivery.mode,
    template_id: delivery.templateId ?? null,
    attachment: delivery.attachment ?? null,
    recipients: delivery.mode === 'to_fixed' ? delivery.recipients : [],
    label_options:
      delivery.attachment === 'pdf_labels' && delivery.labelOptions
        ? labelOptionsToStored(delivery.labelOptions)
        : null,
  };
}

/** Map a raw backend analytics-set to the full `MemberAnalyticsSet` (camelCase config). */
function mapAnalyticsSet(raw: RawAnalyticsSet): MemberAnalyticsSet {
  const delivery = deliveryFromBackend(raw.delivery);
  return {
    id: raw.set_id,
    name: raw.name,
    kind: raw.kind,
    definition: fromBackendConfig(raw.definition ?? {}),
    ...(delivery ? { delivery } : {}),
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

/**
 * GET /members/analytics-sets — list the tenant's member analytics-sets.
 *
 * Unwraps the `{ data: [...] }` envelope and maps each raw entry's
 * `{ set_id, name, kind }` to the summary `{ id, name, kind }` shape. The list is
 * already member-only + tenant-scoped by the Lambda (no client-side filter).
 */
export async function listAnalyticsSets(): Promise<MemberAnalyticsSetSummary[]> {
  const payload = await getJson<unknown>('/members/analytics-sets');
  const rows = unwrapData<unknown>(payload);
  const list = Array.isArray(rows) ? (rows as RawAnalyticsSet[]) : [];
  return list.map((raw) => ({
    id: raw.set_id,
    name: raw.name,
    kind: raw.kind,
    // Surface whether the set has a stored delivery block (R3) so the UI can gate
    // the Schedule action (R5) off the list feed — a schedule needs a delivery.
    hasDelivery: deliveryFromBackend(raw.delivery) !== undefined,
  }));
}

/** GET /members/analytics-sets/{id} — a single analytics-set (full definition). */
export async function getAnalyticsSet(id: string): Promise<MemberAnalyticsSet> {
  const payload = await getJson<unknown>(
    `/members/analytics-sets/${encodeURIComponent(id)}`
  );
  return mapAnalyticsSet(unwrapData<RawAnalyticsSet>(payload));
}

/** POST /members/analytics-sets — create a new analytics-set. */
export async function saveAnalyticsSet(
  name: string,
  config: PivotConfig,
  kind: 'count' | 'list'
): Promise<MemberAnalyticsSet> {
  const payload = await postJson<unknown>('/members/analytics-sets', {
    name,
    kind,
    definition: toBackendConfig(config),
  });
  return mapAnalyticsSet(unwrapData<RawAnalyticsSet>(payload));
}

/** PUT /members/analytics-sets/{id} — update an existing analytics-set. */
export async function updateAnalyticsSet(
  id: string,
  name: string,
  config: PivotConfig,
  kind: 'count' | 'list'
): Promise<MemberAnalyticsSet> {
  const payload = await putJson<unknown>(
    `/members/analytics-sets/${encodeURIComponent(id)}`,
    { name, kind, definition: toBackendConfig(config) }
  );
  return mapAnalyticsSet(unwrapData<RawAnalyticsSet>(payload));
}

/** DELETE /members/analytics-sets/{id} — delete an analytics-set. */
export async function deleteAnalyticsSet(id: string): Promise<void> {
  await deleteJson<unknown>(`/members/analytics-sets/${encodeURIComponent(id)}`);
}

/**
 * PUT /members/analytics-sets/{id}/delivery — set/replace a saved set's optional
 * `delivery` block (R3, design §3; route built concurrently in task 3.3). This is
 * the DEDICATED delivery route: the create/update set bodies (`saveAnalyticsSet`/
 * `updateAnalyticsSet`) deliberately do NOT carry delivery — only this route
 * writes it. The gate is `members:export` + the existing scope (a stored delivery
 * can send only what the user could already export — no new permission).
 *
 * The camelCase {@link MemberDelivery} is mapped to the stored snake_case block
 * via {@link deliveryToBackend} (which also projects the shared `label_options`
 * for a `pdf_labels` attachment and stores NO recipients for `per_recipient`).
 * Returns the updated set with its resolved delivery block.
 */
export async function putAnalyticsSetDelivery(
  id: string,
  delivery: MemberDelivery
): Promise<MemberAnalyticsSet> {
  const payload = await putJson<unknown>(
    `/members/analytics-sets/${encodeURIComponent(id)}/delivery`,
    { delivery: deliveryToBackend(delivery) }
  );
  return mapAnalyticsSet(unwrapData<RawAnalyticsSet>(payload));
}

/**
 * DELETE /members/analytics-sets/{id}/delivery — clear a saved set's `delivery`
 * block (R3, design §3). Same gate as the PUT. The set itself is kept; only the
 * optional delivery instruction is removed (the set reverts to no stored delivery
 * and loads like a legacy set).
 */
export async function deleteAnalyticsSetDelivery(id: string): Promise<void> {
  await deleteJson<unknown>(
    `/members/analytics-sets/${encodeURIComponent(id)}/delivery`
  );
}

// ============================================================================
// Schedules (R5, design §2.3 / §3) — attach a recurring run to a set that HAS a
// delivery block. The Members module OWNS `schedule#<schedule_id>` records in
// DynamoDB (tenant-pinned); EventBridge Scheduler fires each schedule's cron and
// reuses the R4 execute-and-deliver path (task 5.2/5.3, built concurrently).
//
// The route contract is `GET/POST/PUT/DELETE /members/schedules[/{id}]`; a
// schedule carries `{ schedule_id, set_id, cron, enabled, created_by,
// created_at, updated_at }`. These wrappers unwrap the `{ data }` envelope and
// map the snake_case wire form to the camelCase `MemberSchedule`.
//
// Cadence ↔ cron: the editor offers a FRIENDLY cadence (monthly/weekly, design
// §5) and never shows a raw cron. `cadenceToCron` maps a cadence to the concrete
// EventBridge expression the backend stores; `cronToCadence` recovers the
// cadence for the editor when loading an existing schedule (an unrecognized cron
// falls back to `monthly` so the editor still opens).
// ============================================================================

/**
 * The concrete EventBridge cron expression each friendly cadence maps to (design
 * §5). `monthly` runs at 08:00 UTC on the 1st of every month; `weekly` runs at
 * 08:00 UTC every Monday. Kept as a single table so the forward and reverse
 * mappings (and the test) stay in lock-step.
 */
export const CADENCE_CRON: Record<MemberScheduleCadence, string> = {
  monthly: 'cron(0 8 1 * ? *)',
  weekly: 'cron(0 8 ? * MON *)',
};

/** The cadences offered, in display order (keeps the picker + mapping aligned). */
export const SCHEDULE_CADENCES: readonly MemberScheduleCadence[] = [
  'monthly',
  'weekly',
];

/**
 * Map a friendly {@link MemberScheduleCadence} to the backend cron expression
 * (design §5). The UI edits a cadence; this is the ONLY place a cron string is
 * produced for the wire.
 */
export function cadenceToCron(cadence: MemberScheduleCadence): string {
  return CADENCE_CRON[cadence];
}

/**
 * Recover the friendly {@link MemberScheduleCadence} from a stored cron
 * expression so the editor can seed its picker from an existing schedule. An
 * unrecognized expression falls back to `monthly` (the editor still opens; the
 * user can re-pick a cadence and save).
 */
export function cronToCadence(cron: string): MemberScheduleCadence {
  const normalized = (cron ?? '').trim();
  for (const cadence of SCHEDULE_CADENCES) {
    if (CADENCE_CRON[cadence] === normalized) {
      return cadence;
    }
  }
  return 'monthly';
}

/** The raw backend schedule shape (snake_case wire form, string ids). */
interface RawSchedule {
  schedule_id: string;
  set_id: string;
  cron: string;
  enabled?: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

/** Map a raw backend schedule to the camelCase {@link MemberSchedule}. */
function mapSchedule(raw: RawSchedule): MemberSchedule {
  return {
    scheduleId: raw.schedule_id,
    setId: raw.set_id,
    cron: raw.cron,
    enabled: raw.enabled !== false,
    createdBy: typeof raw.created_by === 'string' ? raw.created_by : '',
    createdAt: typeof raw.created_at === 'string' ? raw.created_at : '',
    updatedAt: typeof raw.updated_at === 'string' ? raw.updated_at : '',
  };
}

/**
 * GET /members/schedules — list the tenant's schedules, narrowed to one set.
 *
 * The route returns ALL of the tenant's schedules; a saved set has at most one
 * schedule in this UI, so callers pass the `setId` and this returns only the
 * schedules for that set. Unwraps the `{ data: [...] }` envelope and maps each
 * entry. Tenant-scoped by the Lambda.
 */
export async function listSchedulesForSet(setId: string): Promise<MemberSchedule[]> {
  const payload = await getJson<unknown>('/members/schedules');
  const rows = unwrapData<unknown>(payload);
  const list = Array.isArray(rows) ? (rows as RawSchedule[]) : [];
  return list
    .filter((raw) => raw && raw.set_id === setId)
    .map(mapSchedule);
}

/**
 * POST /members/schedules — create a schedule for a set (R5). The body carries
 * only domain fields (`set_id`, `cron`, `enabled`); `tenant_id`/`created_by`
 * come from the verified token server-side (design §3), never the body. The gate
 * is `members:admin` OR (`members:write` + all-regions) — the backend is
 * authoritative; the UI only offers the action to a capable caller.
 */
export async function createSchedule(
  setId: string,
  cadence: MemberScheduleCadence,
  enabled: boolean
): Promise<MemberSchedule> {
  const payload = await postJson<unknown>('/members/schedules', {
    set_id: setId,
    cron: cadenceToCron(cadence),
    enabled,
  });
  return mapSchedule(unwrapData<RawSchedule>(payload));
}

/**
 * PUT /members/schedules/{id} — update an existing schedule's cadence/enabled
 * state (R5). Same gate as create.
 */
export async function updateSchedule(
  scheduleId: string,
  cadence: MemberScheduleCadence,
  enabled: boolean
): Promise<MemberSchedule> {
  const payload = await putJson<unknown>(
    `/members/schedules/${encodeURIComponent(scheduleId)}`,
    { cron: cadenceToCron(cadence), enabled }
  );
  return mapSchedule(unwrapData<RawSchedule>(payload));
}

/** DELETE /members/schedules/{id} — remove a schedule (R5). Same gate. */
export async function deleteSchedule(scheduleId: string): Promise<void> {
  await deleteJson<unknown>(
    `/members/schedules/${encodeURIComponent(scheduleId)}`
  );
}

// ============================================================================
// Preferred list (per-user, R11.2 layer 2)
//
// One ordered list of TAGGED references per user, keyed server-side by the
// authenticated Cognito `sub` (user ≠ member — R11.1; the client never sends a
// `sub`). `preset:<key>` references a predefined preset (code), `set:<id>` a
// tenant-shared analytics-set. The backend returns `{ sub, refs, updated_at }`
// wrapped in the `{ data }` envelope; an unset list comes back with `refs: []`.
// ============================================================================

/** The raw backend preferred-list shape (`refs` ordered tagged references). */
interface RawPreferredList {
  sub?: string;
  refs?: unknown;
  updated_at?: string;
}

/** Coerce a raw backend preferred-list into the typed `MemberPreferredList`. */
function mapPreferredList(raw: RawPreferredList): MemberPreferredList {
  const refs = Array.isArray(raw.refs)
    ? raw.refs.filter((r): r is string => typeof r === 'string' && r.length > 0)
    : [];
  return {
    sub: typeof raw.sub === 'string' ? raw.sub : '',
    refs,
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : '',
  };
}

/**
 * GET /members/analytics-sets/preferred — the current user's preferred list.
 *
 * Keyed server-side on the authenticated `sub`; returns `refs: []` when the user
 * has never saved a preferred list (empty is valid, not an error — R11.2).
 */
export async function getPreferredList(): Promise<MemberPreferredList> {
  const payload = await getJson<unknown>('/members/analytics-sets/preferred');
  return mapPreferredList(unwrapData<RawPreferredList>(payload));
}

/**
 * PUT /members/analytics-sets/preferred — replace the current user's preferred
 * list with `refs` (a FULL replace — exactly one list per user). Pass `[]` to
 * clear. The backend drops blank/non-string entries and stamps `updated_at`.
 */
export async function savePreferredList(
  refs: string[]
): Promise<MemberPreferredList> {
  const payload = await putJson<unknown>('/members/analytics-sets/preferred', {
    refs,
  });
  return mapPreferredList(unwrapData<RawPreferredList>(payload));
}

// ============================================================================
// Column preferences (Session Columns, R6) — a 1:1 mirror of the preferred-list
// above (`columns` ↔ `refs`). One ordered list of field-config KEYS per user,
// keyed server-side by the authenticated Cognito `sub` (user ≠ member — R11.1;
// the client never sends a `sub`). The backend returns `{ sub, columns,
// updated_at }` wrapped in the `{ data }` envelope; an unset list comes back
// with `columns: []` (empty is valid, not an error — R6.4). The persisted list
// holds field keys only (never member data — R6.6/R6.7); `member_number` is
// implied/always-first and need not be stored (R7.3).
// ============================================================================

/** The raw backend column-preferences shape (`columns` ordered field keys). */
interface RawColumnPreferences {
  sub?: string;
  columns?: unknown;
  updated_at?: string;
}

/** Coerce a raw backend record into the typed `MemberColumnPreferences`. */
function mapColumnPreferences(
  raw: RawColumnPreferences
): MemberColumnPreferences {
  const columns = Array.isArray(raw.columns)
    ? raw.columns.filter(
      (c): c is string => typeof c === 'string' && c.length > 0
    )
    : [];
  return {
    sub: typeof raw.sub === 'string' ? raw.sub : '',
    columns,
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : '',
  };
}

/**
 * GET /members/column-preferences — the current user's chosen overview columns.
 *
 * Keyed server-side on the authenticated `sub`; returns `columns: []` when the
 * user has never saved column preferences (empty is valid, not an error — the
 * page falls back to the admin default, R6.4).
 */
export async function getColumnPreferences(): Promise<MemberColumnPreferences> {
  const payload = await getJson<unknown>('/members/column-preferences');
  return mapColumnPreferences(unwrapData<RawColumnPreferences>(payload));
}

/**
 * PUT /members/column-preferences — replace the current user's chosen columns
 * with `columns` (a FULL replace — exactly one list per user, R6.5). Pass `[]`
 * to clear. The backend drops blank/duplicate/non-candidate keys and stamps
 * `updated_at`.
 */
export async function saveColumnPreferences(
  columns: string[]
): Promise<MemberColumnPreferences> {
  const payload = await putJson<unknown>('/members/column-preferences', {
    columns,
  });
  return mapColumnPreferences(unwrapData<RawColumnPreferences>(payload));
}
