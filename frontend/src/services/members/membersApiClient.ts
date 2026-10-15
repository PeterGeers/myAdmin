/**
 * Members Module API — shared request plumbing (component C7).
 *
 * Extracted verbatim from `membersApiService.ts` (task 5, pure move) so the
 * per-resource client groups (members / column-preferences / config) all share
 * ONE request seam. Nothing here changed behaviourally — see the original
 * module header for the full contract (Bearer JWT + `X-Tenant`/`X-Language`
 * context headers, the single 401 -> refresh -> retry-once path, Bearer-only /
 * no `credentials: 'include'`, and the `{ data: <result> }` envelope).
 *
 * The Members module is a SEPARATE SAM app, NOT the Flask backend: all requests
 * target `MEMBERS_API_BASE_URL` (`import.meta.env.VITE_MEMBERS_API_BASE_URL`).
 *
 * _Requirements: R7.3, R7.4_
 */

import { apiErrorFromResponse } from '../../shared/api/ApiError';
import { getCurrentAuthTokens } from '../authService';

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
export function getMembersApiBaseUrl(): string {
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
export async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

// Thin method helpers so wrappers read cleanly.
export async function getJson<T>(endpoint: string, options: MembersRequestOptions = {}): Promise<T> {
  return handleResponse<T>(await membersRequest(endpoint, { ...options, method: 'GET' }));
}

export async function postJson<T>(
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

export async function putJson<T>(
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

export async function deleteJson<T>(endpoint: string, options: MembersRequestOptions = {}): Promise<T> {
  return handleResponse<T>(await membersRequest(endpoint, { ...options, method: 'DELETE' }));
}

// ============================================================================
// Envelope unwrapping
//
// The Members module wraps EVERY 2xx body as `{ "data": <result> }` (see the
// SAM handler `_response`/`handler`). This helper normalises that so callers
// receive the payload, not the envelope.
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
export function unwrapData<T>(payload: unknown): T {
  if (
    payload !== null &&
    typeof payload === 'object' &&
    'data' in (payload as Record<string, unknown>)
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}
