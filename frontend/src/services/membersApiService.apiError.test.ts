/**
 * membersApiService — structured error surfacing (API standard v1.0, task 4.1).
 *
 * `handleResponse` must throw an `ApiError` on a non-2xx response, preserving the RFC 9457
 * envelope (`status`, `code`, `params`, `errors[]`, `reasons[]`) rather than flattening it to a
 * bare `Error(message)`. A legacy `reasons: string[]` is tolerated; a non-JSON/empty body
 * degrades to `HTTP <status>`; a 2xx still resolves; the 401 refresh/retry path is unchanged.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { getCurrentAuthTokens } from './authService';
import { createMember, transitionMembership, getMember } from './membersApiService';
import { ApiError } from '../shared/api/ApiError';

vi.mock('./authService', () => ({
  getCurrentAuthTokens: vi.fn(),
}));

const mockGetTokens = vi.mocked(getCurrentAuthTokens);

describe('membersApiService — ApiError surfacing', () => {
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

  it('throws an ApiError carrying the 422 field-error array (not a flattened Error)', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 422,
        body: {
          success: false,
          error: 'Validation failed',
          code: 'errors.validation.failed',
          errors: [
            {
              field: 'personal.first_name',
              code: 'errors.validation.required',
              detail: 'is required',
            },
            {
              field: 'membership.status',
              code: 'errors.validation.mustBeOneOf',
              params: { allowed: ['active', 'inactive'] },
              detail: 'must be one of: active, inactive',
            },
          ],
        },
      }),
    );

    const err = await createMember({}).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.code).toBe('errors.validation.failed');
    expect(apiErr.message).toBe('Validation failed'); // legacy `.message` still reads
    expect(apiErr.hasFieldErrors()).toBe(true);
    expect(apiErr.errors).toHaveLength(2);
    expect(apiErr.errors![0]).toMatchObject({
      field: 'personal.first_name',
      code: 'errors.validation.required',
      detail: 'is required',
    });
    expect(apiErr.errors![1].params).toEqual({ allowed: ['active', 'inactive'] });
  });

  it('throws an ApiError carrying the 409 reasons array', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 409,
        body: {
          success: false,
          error: 'Transition denied',
          code: 'errors.transition.denied',
          reasons: [
            { code: 'errors.transition.denied', detail: 'member number required to activate' },
          ],
        },
      }),
    );

    const err = await transitionMembership('M-1', 'MS-1', { to_state: 'active' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(409);
    expect(apiErr.code).toBe('errors.transition.denied');
    expect(apiErr.hasReasons()).toBe(true);
    expect(apiErr.reasons).toHaveLength(1);
    expect((apiErr.reasons as { code: string; detail: string }[])[0].detail).toContain(
      'member number required',
    );
  });

  it('tolerates a legacy reasons: string[] body', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({
        ok: false,
        status: 409,
        body: { success: false, error: 'Transition denied', reasons: ['legacy reason text'] },
      }),
    );

    const err = (await transitionMembership('M-1', 'MS-1', { to_state: 'active' }).catch(
      (e) => e,
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.reasons).toEqual(['legacy reason text']);
  });

  it('degrades to HTTP <status> when the error body is non-JSON/empty', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: async () => {
        throw new Error('not json');
      },
    } as unknown as Response);

    const err = (await createMember({}).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
    expect(err.message).toBe('HTTP 502');
    expect(err.hasFieldErrors()).toBe(false);
    expect(err.hasReasons()).toBe(false);
  });

  it('still resolves a 2xx response (no throw)', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      createMockResponse({ body: { data: { member_id: 'M-9' } } }),
    );
    await expect(getMember('M-9')).resolves.toBeTruthy();
  });
});
