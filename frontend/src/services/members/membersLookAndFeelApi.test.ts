/**
 * Client-level tests for the look-and-feel AUTHORING API (spec 15 — SAM Page Look-and-Feel,
 * task 12.1; design §C3, DD-2; FRONTEND plane, steering 33).
 *
 * These tests pin the Layer-1 authoring CONTRACT the UI must honour (Req 4.1, 4.5, 8.1, 9.1, 9.4):
 *
 *  1. VALUES-ONLY Change-Ops — a set/clear carries ONLY `{ attribute, value }` (one supported
 *     attribute + its value, or `null` to clear), and a copy carries ONLY
 *     `{ op, source_page, target_page }`. The request body must NEVER contain generated CSS
 *     (`cssVariables` / `pageCss` / `fontLinks` / a `:root {` block / a `<style>` tag) and must
 *     NEVER be a whole-record / physical-shape payload (`fields` / `overrides` / `fixed_overrides`
 *     / `field_overlay` / a version stamp). Layer 1 is values-only (design §C3, steering 39).
 *  2. Caller-safe ERROR ENVELOPES from the edge surface WITHOUT leaking internals — a 422
 *     identifying the rejected setting, a 403 cross-tenant/forbidden, and a 409 conflict each come
 *     back as a structured {@link ApiError} carrying the edge's generic message + machine code
 *     (never a Python stack / `str(e)`).
 *
 * The SAM edge is stubbed with MSW so the REAL request plumbing runs end-to-end: `membersRequest`
 * builds the Bearer + `X-Tenant` headers, `handleResponse` parses the 2xx, and
 * `apiErrorFromResponse` turns a non-2xx envelope into the `ApiError` the UI surfaces. The MSW
 * handler ASSERTS the captured request body shape so a regression that smuggles CSS or a whole
 * record into the wire fails the test.
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

import { ApiError } from '../../shared/api/ApiError';
import {
  copyLookAndFeelSettings,
  getLookAndFeelSettings,
  setLookAndFeelSetting,
} from './membersConfigApi';

// ── Test edge base URL + verified-identity stub ──────────────────────────────────────────
//
// The client resolves its base URL from VITE_MEMBERS_API_BASE_URL (fail-fast) and attaches a
// Bearer id-token + X-Tenant from getCurrentAuthTokens / localStorage. Stub both so the REAL
// request plumbing runs against the MSW-stubbed edge.
const BASE_URL = 'https://members.test.example';

vi.mock('../authService', () => ({
  getCurrentAuthTokens: vi.fn(async () => ({ idToken: 'test-id-token' })),
}));

// The two routes under test. The PUT handler captures the body of the LAST request so each test
// can assert the exact wire shape the UI sent.
let lastPutBody: any = null;

const server = setupServer(
  http.get(`${BASE_URL}/members/look-and-feel`, () =>
    // The module `{ data }` envelope; GET resolves the stored VALUES (absent → empty map).
    HttpResponse.json({
      success: true,
      data: { settings: { color_primary: '#2D5F8A', base_spacing: 'relaxed' } },
    }),
  ),
  http.put(`${BASE_URL}/members/look-and-feel`, async ({ request }) => {
    lastPutBody = await request.json();
    return HttpResponse.json({ success: true, data: { settings: {} } });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  lastPutBody = null;
  vi.stubEnv('VITE_MEMBERS_API_BASE_URL', BASE_URL);
  localStorage.setItem('selectedTenant', 'h-dcn');
});

afterEach(() => {
  vi.unstubAllEnvs();
  localStorage.clear();
});

/**
 * A body is "values-only" when it contains NONE of the forbidden shapes: no generated CSS, and no
 * whole-record / physical-storage keys. This is the assertion that guards the Layer-1 contract
 * (Req 8.1, steering 39) — the single most important thing this suite protects.
 */
function assertNoCssOrWholeRecord(body: Record<string, unknown>): void {
  const serialized = JSON.stringify(body);

  // (a) No generated CSS anywhere in the payload (Layer 2 owns CSS; Layer 1 never sends it).
  for (const cssKey of ['css', 'cssVariables', 'cssVariableMap', 'pageCss', 'fontLinks', 'style']) {
    expect(body).not.toHaveProperty(cssKey);
  }
  expect(serialized).not.toContain(':root {');
  expect(serialized).not.toContain('<style');
  expect(serialized).not.toMatch(/--[a-z-]+:/); // no CSS custom-property declarations

  // (b) No whole-record / physical-shape payload (the raw config#fields layout stays server-side).
  for (const rawKey of [
    'fields',
    'overrides',
    'fixed_overrides',
    'field_overlay',
    'functional_groups',
    'version',
    'sk',
    'tenant_id',
  ]) {
    expect(body).not.toHaveProperty(rawKey);
  }
}

describe('setLookAndFeelSetting — VALUES-ONLY set Change-Op (Req 4.1, 8.1)', () => {
  it('sends ONLY { attribute, value } — never CSS, never a whole record', async () => {
    await setLookAndFeelSetting('color_primary', '#123456');

    expect(lastPutBody).toEqual({ attribute: 'color_primary', value: '#123456' });
    assertNoCssOrWholeRecord(lastPutBody);
    // Exactly the two authoring keys — nothing smuggled alongside.
    expect(Object.keys(lastPutBody).sort()).toEqual(['attribute', 'value']);
  });

  it('clears an attribute with an explicit null value (revert to default), still values-only', async () => {
    await setLookAndFeelSetting('shadow_style', null);

    expect(lastPutBody).toEqual({ attribute: 'shadow_style', value: null });
    assertNoCssOrWholeRecord(lastPutBody);
  });

  it('carries an optional page id without widening into a whole-record payload', async () => {
    await setLookAndFeelSetting('font_heading', 'Inter', 'application_form');

    expect(lastPutBody).toEqual({
      attribute: 'font_heading',
      value: 'Inter',
      page: 'application_form',
    });
    assertNoCssOrWholeRecord(lastPutBody);
  });
});

describe('copyLookAndFeelSettings — VALUES-ONLY copy Change-Op (Req 9.1)', () => {
  it('sends the copy op by page identity — never CSS, never a whole record', async () => {
    await copyLookAndFeelSettings('landing_page', 'application_form');

    expect(lastPutBody).toEqual({
      op: 'copy',
      source_page: 'landing_page',
      target_page: 'application_form',
    });
    assertNoCssOrWholeRecord(lastPutBody);
  });

  it('defaults both page ids server-side when the UI omits them', async () => {
    await copyLookAndFeelSettings();
    expect(lastPutBody).toEqual({ op: 'copy' });
    assertNoCssOrWholeRecord(lastPutBody);
  });
});

describe('getLookAndFeelSettings — resolves stored VALUES (Req 2.3)', () => {
  it('unwraps the { data } envelope to the stored values map', async () => {
    const result = await getLookAndFeelSettings();
    expect(result.settings).toEqual({ color_primary: '#2D5F8A', base_spacing: 'relaxed' });
  });
});

describe('caller-safe error envelopes surface without leaking internals (Req 4.5, 9.4)', () => {
  it('surfaces a 422 validation rejection identifying the rejected setting (Req 4.5)', async () => {
    server.use(
      http.put(`${BASE_URL}/members/look-and-feel`, () =>
        HttpResponse.json(
          {
            success: false,
            error: 'shadow_style must be one of: none, subtle, medium, dramatic',
            code: 'errors.validation.failed',
          },
          { status: 422 },
        ),
      ),
    );

    const err = await setLookAndFeelSetting('shadow_style', 'neon').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe('errors.validation.failed');
    // The message names the client's OWN rejected setting — safe to surface — and carries no
    // internal detail (no stack frame, no Python traceback marker).
    expect(err.message).toContain('shadow_style');
    expect(err.message).not.toMatch(/Traceback|File "|line \d+|str\(e\)/);
  });

  it('surfaces a 403 forbidden for a cross-tenant copy without confirming the other tenant (Req 9.4)', async () => {
    server.use(
      http.put(`${BASE_URL}/members/look-and-feel`, () =>
        HttpResponse.json(
          { success: false, error: 'Forbidden', code: 'errors.api.forbidden' },
          { status: 403 },
        ),
      ),
    );

    const err = await copyLookAndFeelSettings('other_tenant_page', 'application_form').catch(
      (e) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe('errors.api.forbidden');
    // Generic — never leaks whether the other tenant / page exists.
    expect(err.message).toBe('Forbidden');
  });

  it('surfaces a 409 conflict (stale version) as a reload-and-retry signal', async () => {
    server.use(
      http.put(`${BASE_URL}/members/look-and-feel`, () =>
        HttpResponse.json(
          {
            success: false,
            error: 'This was changed by someone else — reload and try again',
            code: 'errors.api.conflict',
          },
          { status: 409 },
        ),
      ),
    );

    const err = await setLookAndFeelSetting('color_accent', '#F4A261').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe('errors.api.conflict');
    expect(err.message).not.toMatch(/Traceback|File "|str\(e\)/);
  });
});
