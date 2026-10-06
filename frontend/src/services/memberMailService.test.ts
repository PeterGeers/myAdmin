/**
 * Unit tests for memberMailService (services/memberMailService.ts).
 *
 * Verifies the typed result shaping, with task 9.3's SES rate-limit branch
 * (R4.12) in focus:
 *   - a successful send yields `{ success: true, status, recipientCount, ... }`;
 *   - a 429 (or a body `code: 'rate_limited'`) is flagged `rateLimited: true` so
 *     the compose UI can surface the dedicated message and keep the set;
 *   - any other non-2xx is a generic failure (`rateLimited` falsy).
 *
 * The underlying authenticated POST is mocked — no network.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';

// --- Mock the authenticated transport (no network). --------------------------
const authenticatedPost = vi.fn();
vi.mock('./apiService', () => ({
  authenticatedPost: (...args: unknown[]) => authenticatedPost(...args),
  buildEndpoint: (path: string) => path,
}));

import { mailMembersSet } from './memberMailService';

/** Build a minimal Response-like stub the service consumes (`ok`, `status`, `json`). */
function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

const request = {
  recipients: ['alice@example.com'],
  subject: 's',
  body: 'b',
};

beforeEach(() => {
  authenticatedPost.mockReset();
});

describe('mailMembersSet', () => {
  it('shapes a successful send into a typed success result', async () => {
    authenticatedPost.mockResolvedValue(
      jsonResponse(200, { success: true, recipient_count: 3, message_id: 'm-1' }),
    );

    const result = await mailMembersSet(request);

    expect(result.success).toBe(true);
    expect(result.status).toBe(200);
    expect(result.recipientCount).toBe(3);
    expect(result.messageId).toBe('m-1');
    expect(result.rateLimited).toBeFalsy();
  });

  it('flags a 429 as rateLimited (SES throttle, R4.12/task 9.3)', async () => {
    authenticatedPost.mockResolvedValue(
      jsonResponse(429, {
        error: 'Email send rate limit reached',
        code: 'rate_limited',
        message: 'Throttling: Maximum sending rate exceeded',
      }),
    );

    const result = await mailMembersSet(request);

    expect(result.success).toBe(false);
    expect(result.status).toBe(429);
    expect(result.rateLimited).toBe(true);
    expect(result.error).toBeTruthy();
  });

  it("flags a rate limit from the body code even on a non-429 status", async () => {
    authenticatedPost.mockResolvedValue(
      jsonResponse(503, { error: 'busy', code: 'rate_limited' }),
    );

    const result = await mailMembersSet(request);

    expect(result.success).toBe(false);
    expect(result.rateLimited).toBe(true);
  });

  it('treats any other failure as a generic (non-rate-limited) error', async () => {
    authenticatedPost.mockResolvedValue(
      jsonResponse(502, { error: 'Failed to send email', message: 'MessageRejected' }),
    );

    const result = await mailMembersSet(request);

    expect(result.success).toBe(false);
    expect(result.status).toBe(502);
    expect(result.rateLimited).toBeFalsy();
    expect(result.error).toBe('Failed to send email');
  });
});
