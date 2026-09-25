/**
 * Shared structured API error — the frontend half of the platform API response & error
 * standard v1.0 (steering `37`; spec `Common/Frameworks/api-response-standard`).
 *
 * Every backend (SAM + Flask) returns the envelope
 *   `{ success, data | error, code?, params?, errors?, reasons? }`
 * with a real HTTP status. On a non-2xx response a service throws an {@link ApiError} that
 * preserves that whole structure — `status`, the machine `code`, interpolation `params`, the
 * RFC 9457 per-field `errors[]` array, and the `reasons[]` array — instead of collapsing it into
 * a bare `Error(message)`. `applyApiError` then surfaces it (localized inline field errors +
 * summary toast).
 *
 * Backward compatible: `ApiError extends Error`, so any existing `catch` that only reads
 * `err.message` keeps working (the message is the backend English `error`, or `HTTP <status>`).
 *
 * This lives under `frontend/src/shared/api/` — a DISCOVERABLE, cross-cutting home (per C6), NOT
 * inside a feature folder — because both the Members module and the Flask surfaces consume it.
 */

/** One RFC 9457 per-field error entry (the 422 `errors[]` array items). */
export interface FieldErrorEntry {
  /** Dotted field key, e.g. `personal.first_name` (matched to a form field by `applyApiError`). */
  field: string;
  /** Machine i18n code, e.g. `errors.validation.required` — resolved via `t(code, params)`. */
  code: string;
  /** Optional interpolation values for the i18n template (e.g. `{ allowed: [...] }`). */
  params?: Record<string, unknown>;
  /** Human English fallback (the backend's message) shown when `code` cannot be resolved. */
  detail: string;
}

/** One RFC 9457 reason entry (the 409 `reasons[]` array items — no `field`). */
export interface ReasonEntry {
  /** Machine i18n code, e.g. `errors.transition.denied`. */
  code: string;
  /** Optional interpolation values. */
  params?: Record<string, unknown>;
  /** Human English fallback. */
  detail: string;
}

/** The parsed shape of a non-2xx error body (all members optional — degrade gracefully). */
export interface ApiErrorBody {
  error?: string;
  /** Legacy alternative to `error` (some older endpoints use `message`); honored as a fallback. */
  message?: string;
  code?: string;
  params?: Record<string, unknown>;
  /** RFC 9457 array (v1.0). A legacy `string[]` is tolerated by `ApiError` / `applyApiError`. */
  errors?: FieldErrorEntry[];
  reasons?: ReasonEntry[] | string[];
}

/**
 * A thrown API error carrying the full standard envelope.
 *
 * `message` (from `Error`) is the backend English `error` (or `HTTP <status>`), so legacy
 * `catch (e) { toast(e.message) }` still reads. `applyApiError` prefers the structured members.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly params?: Record<string, unknown>;
  readonly errors?: FieldErrorEntry[];
  readonly reasons?: ReasonEntry[] | string[];

  constructor(status: number, body: ApiErrorBody) {
    // `error` is the standard field; `message` is a legacy fallback some older endpoints use;
    // else the generic `HTTP <status>` (backward compatible with the old handleResponse).
    super(body.error || body.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.params = body.params;
    this.errors = body.errors;
    this.reasons = body.reasons;
    // Restore the prototype chain (needed when targeting ES5 / transpiled classes) so
    // `instanceof ApiError` holds for callers that branch on it.
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  /** True when the error carries RFC 9457 per-field entries (a 422 the SPA renders inline). */
  hasFieldErrors(): boolean {
    return Array.isArray(this.errors) && this.errors.length > 0;
  }

  /** True when the error carries reason entries (a 409 transition denial). */
  hasReasons(): boolean {
    return Array.isArray(this.reasons) && this.reasons.length > 0;
  }
}

/**
 * Build an {@link ApiError} from a `Response`, parsing the JSON body (tolerant of a non-JSON /
 * empty body → `{}`, so `message` degrades to `HTTP <status>`). A service's `handleResponse`
 * calls this on `!response.ok`.
 */
export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const body: ApiErrorBody = await response
    .json()
    .catch(() => ({} as ApiErrorBody));
  return new ApiError(response.status, body);
}
