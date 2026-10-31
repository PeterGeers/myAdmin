/**
 * Public Member-Application API Service (spec Members/application-app, task 9.1).
 *
 * The frontend seam for the PUBLIC, UNAUTHENTICATED member-application intake. It
 * reaches the SEPARATE public SAM API (design D27 — its OWN `AWS::Serverless::Api`
 * with no `DefaultAuthorizer`, own invoke URL), NOT the authenticated Members API
 * (`membersApiService`) and NOT the Flask backend (`apiService`).
 *
 * Why its own service (mirrors `publicLandingService.ts`):
 *  - the authenticated services attach a Cognito Bearer token + `X-Tenant`; a public
 *    applicant has NEITHER (R1.1). Routing through them would force inappropriate auth
 *    headers onto an unauthenticated endpoint and hit the wrong origin.
 *  - the target is the public intake API base (`VITE_PUBLIC_MEMBERS_API_BASE_URL`),
 *    resolved fail-fast (no silent fallback to a wrong/relative base), mirroring the
 *    Members API base-URL contract.
 *
 * SCOPE (task 9.1): this covers the field-config READ (`GET …/field-config`) that drives
 * the config-driven renderer, plus the shared public contract TYPES. The submit POST
 * (422→Formik, task 9.3) and the readiness-gate 409 / 404 handling (task 9.4) layer on
 * top of this seam; the discriminated `FieldConfigResult` already carries the `notAvailable`
 * and `notFound` arms so those tasks slot in without reshaping this module.
 *
 * _Requirements: R1, R1a, R4, R5, R5.4, R6b, R10a.4_
 */

// ============================================================================
// Public field-config contract (design §3.1 `ResolvedPublicField` + the 200 body)
//
// CONSOLIDATION (task 9.3): the contract now lives in ONE place —
// `components/public/application/applicationFieldConfig.ts` — shared by the renderer (9.1), the
// Yup generator (9.2), and this submit seam (9.3). This module RE-EXPORTS it so its own public
// surface (and the task-9.1 tests that import these names from here) is unchanged.
// ============================================================================

export type {
  PublicFieldFormat,
  PublicFieldOption,
  PublicChoiceEntry,
  PublicField,
  PublicConsentNotice,
  PublicFieldConfig,
} from '../components/public/application/applicationFieldConfig';

import type { PublicFieldConfig } from '../components/public/application/applicationFieldConfig';
import { API_BASE_URL } from '../config/api';

/**
 * Result of loading a tenant's public field-config — a discriminated union so the page
 * (task 9.4) renders each arm without inspecting status codes:
 *  - `success`      — the schema to drive the renderer (200);
 *  - `not_available`— the tenant is not send-ready / not accepting applications (409, D15/R5.4);
 *  - `not_found`    — unknown/forged slug, non-probeable (404, R1a.4);
 *  - `error`        — transport/parse failure.
 */
export type FieldConfigResult =
  | { status: 'success'; data: PublicFieldConfig }
  | { status: 'not_available'; code: string }
  | { status: 'not_found' }
  | { status: 'error'; message: string };

// ============================================================================
// Base URL resolution (fail-fast, mirrors membersApiClient.getMembersApiBaseUrl)
// ============================================================================

/**
 * Resolve the PUBLIC member-application API base URL, failing fast when unset/blank.
 *
 * Reads `import.meta.env.VITE_PUBLIC_MEMBERS_API_BASE_URL` (the separate public SAM API,
 * D27 — distinct from the authenticated `VITE_MEMBERS_API_BASE_URL`). Resolved lazily on
 * first request (testable; does not break unrelated imports) with the same no-silent-fallback
 * contract as the Members API seam. A single trailing slash is normalised away.
 *
 * @throws Error when the env var is unset or blank.
 */
export function getPublicApplicationApiBaseUrl(): string {
  const raw = import.meta.env.VITE_PUBLIC_MEMBERS_API_BASE_URL as string | undefined;
  const base = (raw ?? '').trim();
  if (!base) {
    throw new Error(
      'VITE_PUBLIC_MEMBERS_API_BASE_URL is not set. The public member-application API ' +
      'base URL must be configured (see frontend/.env.local / .env.example).',
    );
  }
  return base.replace(/\/+$/, '');
}

// ============================================================================
// Field-config READ (GET /public/members/{slug}/field-config)
// ============================================================================

/**
 * Fetch the public field-config for a tenant slug — the readiness gate + the schema the
 * config-driven renderer is built from (design §2.1, R5).
 *
 * Public + unauthenticated by design: NO Bearer token, NO `X-Tenant`. The slug is carried in
 * the path (D3/D19) and resolved server-side against the allow-list — a forged slug returns a
 * non-probeable 404 (R1a.4). Unwraps the standard `{ data: … }` envelope (R1a) when present.
 *
 * @param tenantSlug - The tenant slug segment from the public route.
 * @param options - Optional overrides: a pre-resolved `baseUrl` and an `AbortSignal` so the
 *   caller can cancel an in-flight request on unmount.
 */
export async function fetchPublicFieldConfig(
  tenantSlug: string,
  options: { baseUrl?: string; signal?: AbortSignal } = {},
): Promise<FieldConfigResult> {
  let baseUrl: string;
  try {
    baseUrl = options.baseUrl ?? getPublicApplicationApiBaseUrl();
  } catch (err) {
    return { status: 'error', message: (err as Error).message };
  }

  const url = `${baseUrl}/public/members/${encodeURIComponent(tenantSlug)}/field-config`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: options.signal,
    });

    // Unknown/forged slug — non-probeable 404 (R1a.4), rendered as "not found".
    if (response.status === 404) {
      return { status: 'not_found' };
    }

    // Tenant not send-ready / not accepting applications — neutral 409 (D15/R5.4). We read
    // the stable `code` (envelope) WITHOUT exposing mail-config internals (R5.4 neutral).
    if (response.status === 409) {
      const code = await readErrorCode(response);
      return { status: 'not_available', code };
    }

    if (!response.ok) {
      return { status: 'error', message: `Failed to load form (${response.status})` };
    }

    const payload = unwrapData<PublicFieldConfig>(await response.json());
    return { status: 'success', data: payload };
  } catch (err) {
    // An aborted fetch is a deliberate cancel (unmount) — surface it so the caller can ignore it.
    if ((err as Error)?.name === 'AbortError') {
      return { status: 'error', message: 'aborted' };
    }
    return { status: 'error', message: 'Failed to load form' };
  }
}

// ============================================================================
// Branding-logo READ — spec 13 R5 (option 1: public CloudFront logo URL)
//
// `GET {API_BASE_URL}/api/public/landing/<slug>/logo` returns
// `{ success, data: { logo: <https-url> | null } }` where `logo` is the tenant's
// PUBLIC `landing_page.logo_url` — the public-pages CloudFront URL of the uploaded
// logo (a plain, world-reachable image the form just `<img src>`s). It is NOT
// gated on a PUBLISHED landing page (the URL is set on upload), so the form shows
// the logo whether or not a landing page exists (spec 13 R5.2).
//
// This Flask read is reached via `API_BASE_URL` — the SAME origin the public
// landing page's contact form posts to, so it is reachable from the public page.
// (Round-1 returned an inline base64 data URI from the PROTECTED branding bucket;
// that source was not public and could not render — retired.)
//
// A missing logo (null, 404, or ANY transport/parse failure) is a graceful
// "no logo" — never an error that blocks the form (R5.3).
// ============================================================================

/**
 * Fetch the tenant's branding logo for the public application form (R5.2/R5.3).
 *
 * Returns the logo as an inline data URI when the tenant has one configured, or `null`
 * when it is absent/unconfigured OR when the read fails for any reason — a missing logo
 * must NEVER block or error the form (R5.3). The slug is carried in the path and resolved
 * server-side; no auth, no `X-Tenant`.
 *
 * @param tenantSlug - The tenant slug segment from the public route.
 * @param options - Optional overrides: a pre-resolved Flask `baseUrl` (tests inject it;
 *   production uses the app's `API_BASE_URL`) and an `AbortSignal` for unmount cancel.
 * @returns The logo data URI, or `null` for "no logo".
 */
export async function fetchPublicLogo(
  tenantSlug: string,
  options: { baseUrl?: string; signal?: AbortSignal } = {},
): Promise<string | null> {
  // Reached on the Flask plane via `API_BASE_URL` (the same origin the landing contact form
  // posts to); `options.baseUrl` overrides it in tests. The endpoint returns the tenant's
  // public `logo_url` (a CloudFront image URL) or null.
  const rawBase = options.baseUrl ?? API_BASE_URL;
  const baseUrl = (rawBase ?? '').replace(/\/+$/, '');
  const url = `${baseUrl}/api/public/landing/${encodeURIComponent(tenantSlug)}/logo`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: options.signal,
    });

    // Any non-2xx (404 unknown slug, 5xx, etc.) is simply "no logo" — never a blocker (R5.3).
    if (!response.ok) return null;

    const payload = unwrapData<{ logo?: unknown }>(await response.json());
    const logo = payload?.logo;
    // A plain https CloudFront URL string; blank/absent → "no logo".
    return typeof logo === 'string' && logo.trim().length > 0 ? logo.trim() : null;
  } catch {
    // Aborted fetch, network error, or parse failure — all degrade to "no logo" (R5.3).
    return null;
  }
}

/** Read the machine `code` off an error envelope, degrading to a stable default. */
async function readErrorCode(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { code?: unknown };
    if (body && typeof body.code === 'string') return body.code;
  } catch {
    // non-JSON / empty body — fall through to the default.
  }
  return 'errors.application.notAvailable';
}

/** Unwrap the SAM module's `{ data: <result> }` envelope (R1a); tolerate a bare payload. */
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

// ============================================================================
// Flatten ↔ un-flatten (R10a.4)
//
// The renderer keeps FLAT form state keyed by each field's DOTTED key. The submit shape the
// backend accepts (design §3.2) is the SAME flat `{ dotted_key: value }` map (optionally wrapped
// under a `fields` key). These helpers convert between the flat form state and the nested member
// shape (`{ personal:{…}, overlay:{…} }`) so a caller/test can round-trip either direction — the
// renderer's own value map is already the flat submit shape, and un-flatten mirrors the server's
// `un-flatten to nested` (R4.7) for parity checks.
// ============================================================================

/**
 * Flatten a NESTED member-shape object (`{ personal:{ first_name:'A' }, overlay:{ iban:'…' } }`)
 * into the flat dotted-key map (`{ 'personal.first_name':'A', 'overlay.iban':'…' }`) the form
 * state uses. Only leaf scalars are flattened; a `null`/`undefined` leaf is preserved as-is.
 */
export function flattenFields(
  nested: Record<string, unknown>,
  prefix = '',
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(nested)) {
    const dotted = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(out, flattenFields(value as Record<string, unknown>, dotted));
    } else {
      out[dotted] = value;
    }
  }
  return out;
}

/**
 * Un-flatten a flat dotted-key map (`{ 'personal.first_name':'A' }`) back into the NESTED member
 * shape (`{ personal:{ first_name:'A' } }`) the create path expects (R4.7). A bare (un-dotted)
 * key lands at the top level. Later keys win on a collision; intermediate non-object nodes are
 * overwritten with an object so a deeper key can nest.
 */
export function unflattenFields(flat: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [dotted, value] of Object.entries(flat)) {
    const parts = dotted.split('.');
    let node = out;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      const next = node[part];
      if (next === null || typeof next !== 'object' || Array.isArray(next)) {
        node[part] = {};
      }
      node = node[part] as Record<string, unknown>;
    }
    node[parts[parts.length - 1]] = value;
  }
  return out;
}

// ============================================================================
// Submit (POST /public/members/{slug}/applications) — task 9.3
//
// The submit seam. The server is AUTHORITATIVE (R2.3/R6.6): its 422 `errors[]`
// (`_field_errors_array`, `{field,code,detail}`, R1a.3) is surfaced VERBATIM as a
// discriminated `validation_error` arm so the page can map each entry into Formik BY
// the dotted `field` key (R10a.3). The success path is a neutral 202 with no `member_id`
// (R1a.2). The caller un-flattens the form values into the nested member shape before POST
// (R4.7) — this service sends exactly what it is given.
// ============================================================================

/** One server field error from the R1a 422 `errors[]` array (`_field_errors_array`). */
export interface ApplicationFieldError {
  /** The DOTTED field key the error targets — the Formik map key (R10a.3). */
  field: string;
  /** Stable machine code the SPA localizes (api-response-standard v1.0). */
  code: string;
  /** English fallback detail (localized by `code` where a message exists). */
  detail?: string;
}

/** The affirmative consent payload (F4/R12.1). The server stamps version/accepted_at (2.6). */
export interface ApplicationConsent {
  /** Affirmative acceptance — a submit without this is rejected server-side (R12.1). */
  accepted: boolean;
  /** The versioned notice id the applicant accepted (D26); the server is authoritative. */
  notice_version?: string;
}

/** The submit request body (design §3.2). `fields` is the flat `{ dotted_key: value }` map. */
export interface ApplicationSubmitRequest {
  /** Session de-dup key (R3a) — a resend with the same key UPDATES the same record. */
  session_key?: string;
  /** Applicant locale driving the confirmation email (R6b, default nl). */
  locale: string;
  /** Affirmative consent (R12.1); the server stamps version/accepted_at authoritatively (2.6). */
  consent: ApplicationConsent;
  /** Anti-bot honeypot (R10.2) — expected empty; a filled value trips a 400 server-side. */
  honeypot?: string;
  /** The flat `{ dotted_key: value }` submission (design §3.2). */
  fields: Record<string, unknown>;
}

/**
 * Result of a submit — a discriminated union so the page renders each arm without re-reading
 * status codes:
 *  - `accepted`         — neutral 202, record written, notifications offloaded (R1a.2);
 *  - `validation_error` — 422 with the server `errors[]` to map into Formik by dotted key (R10a.3);
 *  - `not_available`    — readiness gate refused on direct submit (409, D15/R9.4);
 *  - `not_found`        — unknown/forged slug, non-probeable (404, R1a.4);
 *  - `error`            — transport/other failure.
 */
export type SubmitApplicationResult =
  | { status: 'accepted' }
  | { status: 'validation_error'; errors: ApplicationFieldError[]; code: string }
  | { status: 'not_available'; code: string }
  | { status: 'not_found' }
  | { status: 'error'; message: string };

/**
 * Submit a member application to the public endpoint (design §2.2 / §3.2, R1a).
 *
 * Public + unauthenticated: NO Bearer token, NO `X-Tenant`; the slug is in the path and resolved
 * server-side (R1a.4). The server stays authoritative — a 422 is returned as the raw `errors[]`
 * (dotted `field`, `code`, `detail`) for the page to merge into Formik (R10a.3), winning over any
 * client Yup error. A 404 is non-probeable; a 409 is the neutral readiness refusal (R9.4).
 */
export async function submitApplication(
  tenantSlug: string,
  body: ApplicationSubmitRequest,
  options: { baseUrl?: string; signal?: AbortSignal } = {},
): Promise<SubmitApplicationResult> {
  let baseUrl: string;
  try {
    baseUrl = options.baseUrl ?? getPublicApplicationApiBaseUrl();
  } catch (err) {
    return { status: 'error', message: (err as Error).message };
  }

  const url = `${baseUrl}/public/members/${encodeURIComponent(tenantSlug)}/applications`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      return { status: 'error', message: 'aborted' };
    }
    return { status: 'error', message: 'Failed to submit application' };
  }

  // Unknown/forged slug — non-probeable 404 (R1a.4).
  if (response.status === 404) {
    return { status: 'not_found' };
  }

  // Validation failure — 422 carrying the authoritative `errors[]` (R1a.3/R10a.3).
  if (response.status === 422) {
    const parsed = await parseErrorBody(response);
    return {
      status: 'validation_error',
      errors: parsed.errors,
      code: parsed.code || 'errors.validation.failed',
    };
  }

  // Readiness gate refused on direct submit — neutral 409 (D15/R9.4).
  if (response.status === 409) {
    const parsed = await parseErrorBody(response);
    return { status: 'not_available', code: parsed.code || 'errors.application.notAvailable' };
  }

  if (!response.ok) {
    return { status: 'error', message: `Failed to submit application (${response.status})` };
  }

  // 2xx (202 Accepted, R1a.2) — neutral success; no member_id is read from the body.
  return { status: 'accepted' };
}

/** Parse an error envelope into its `code` + the `errors[]` array, degrading gracefully. */
async function parseErrorBody(
  response: Response,
): Promise<{ code: string; errors: ApplicationFieldError[] }> {
  try {
    const raw = (await response.json()) as unknown;
    const body = unwrapData<Record<string, unknown>>(raw) ?? {};
    const envelope = (raw ?? {}) as Record<string, unknown>;
    // `code` may sit on the envelope or the unwrapped body depending on the shape.
    const code =
      (typeof envelope.code === 'string' && envelope.code) ||
      (typeof body.code === 'string' && body.code) ||
      '';
    const rawErrors = Array.isArray(body.errors)
      ? body.errors
      : Array.isArray(envelope.errors)
        ? envelope.errors
        : [];
    const errors: ApplicationFieldError[] = [];
    for (const entry of rawErrors as unknown[]) {
      if (entry && typeof entry === 'object') {
        const e = entry as Record<string, unknown>;
        if (typeof e.field === 'string') {
          errors.push({
            field: e.field,
            code: typeof e.code === 'string' ? e.code : '',
            detail: typeof e.detail === 'string' ? e.detail : undefined,
          });
        }
      }
    }
    return { code, errors };
  } catch {
    return { code: '', errors: [] };
  }
}
