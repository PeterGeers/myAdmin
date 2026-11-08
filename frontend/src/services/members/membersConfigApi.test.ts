/**
 * Client-level tests for the slug/prefix author methods in membersConfigApi.
 *
 * REGRESSION (findings.md — "Saving the prefix failed" on a 200): the SAM platform envelope is
 * `{ success: true, data: <serviceResult> }` with `success` at the TOP level. `unwrapData` returns
 * only `data` (here `{ version, idempotent_replay }` — NO `success`), so a client method that
 * returned the bare unwrapped value gave the caller `res.success === undefined` → the builder
 * reported a successful write as a failure. These tests exercise the REAL client methods against a
 * mocked `postJson` returning the REAL envelope and assert `success: true` is surfaced.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock ONLY the transport (postJson); use the REAL unwrapData so the envelope-stripping behaviour
// under test is the production one.
const mockPostJson = vi.fn();
vi.mock('./membersApiClient', async () => {
  const actual = await vi.importActual<typeof import('./membersApiClient')>(
    './membersApiClient',
  );
  return {
    ...actual,
    postJson: (...a: unknown[]) => mockPostJson(...a),
  };
});

import { setApplicationFormSlug, setApplicationFormPrefix } from './membersConfigApi';

// The exact success envelope the SAM edge returns for a config#fields Change-Op write
// (see sam/members/handler/_http.py::_response — success derived from the 2xx status).
const ENVELOPE = {
  success: true,
  data: { version: '2026-11-03T13:58:09.311481+00:00', idempotent_replay: false },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockPostJson.mockResolvedValue(ENVELOPE);
});

describe('setApplicationFormPrefix', () => {
  it('surfaces success:true from the platform envelope on a 2xx write (regression: findings.md)', async () => {
    const res = await setApplicationFormPrefix('hdcn');
    expect(mockPostJson).toHaveBeenCalledWith('/members/application-form/prefix', {
      prefix: 'hdcn',
    });
    expect(res.success).toBe(true);
    expect(res.prefix).toBe('hdcn');
    expect(res.version).toBe('2026-11-03T13:58:09.311481+00:00');
  });

  it('echoes a null (clear) prefix with success:true', async () => {
    const res = await setApplicationFormPrefix(null);
    expect(mockPostJson).toHaveBeenCalledWith('/members/application-form/prefix', {
      prefix: null,
    });
    expect(res.success).toBe(true);
    expect(res.prefix).toBeNull();
  });
});

describe('setApplicationFormSlug', () => {
  it('surfaces success:true from the platform envelope on a 2xx write (regression: findings.md)', async () => {
    const res = await setApplicationFormSlug('hdcn-aanmelden');
    expect(mockPostJson).toHaveBeenCalledWith('/members/application-form/slug', {
      slug: 'hdcn-aanmelden',
    });
    expect(res.success).toBe(true);
    expect(res.slug).toBe('hdcn-aanmelden');
    expect(res.version).toBe('2026-11-03T13:58:09.311481+00:00');
  });

  it('echoes a null (clear) slug with success:true', async () => {
    const res = await setApplicationFormSlug(null);
    expect(res.success).toBe(true);
    expect(res.slug).toBeNull();
  });
});
