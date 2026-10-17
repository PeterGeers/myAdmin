/**
 * Member sender-identity service - Unit Tests (R0, design §6.2).
 *
 * Verifies each function hits the correct FLASK route + method with the
 * authenticated headers, and that the single-identity Flask envelope is adapted
 * to the list-shaped UI contract (Option A, single active sender per tenant).
 */
import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import {
  getSenderIdentities,
  addSenderIdentity,
  resendSenderIdentity,
} from './memberSenderIdentityService';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('memberSenderIdentityService', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'club';

  beforeEach(() => {
    vi.clearAllMocks();

    Storage.prototype.getItem = vi.fn((key) => {
      if (key === 'selectedTenant') return mockTenant;
      return null;
    });

    mockFetchAuthSession.mockResolvedValue({
      tokens: { idToken: { toString: () => mockToken } },
    } as any);

    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getSenderIdentities', () => {
    it('GETs the Flask sender-identities route and wraps the single identity into a list', async () => {
      // Flask returns a SINGLE identity under `data` (snake_case last_checked).
      const body = {
        success: true,
        data: { email: 'a@club.nl', status: 'verified', last_checked: null },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await getSenderIdentities();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/members/sender-identities'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Authorization: `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      // Adapted to the list-shaped UI contract (camelCase lastChecked).
      expect(result).toEqual({
        success: true,
        data: {
          identities: [{ email: 'a@club.nl', status: 'verified', lastChecked: null }],
        },
      });
    });

    it('returns an empty identities[] when the tenant has no sender yet', async () => {
      const body = { success: true, data: { email: null, status: null, last_checked: null } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await getSenderIdentities();

      expect(result).toEqual({ success: true, data: { identities: [] }, error: undefined, code: undefined });
    });
  });

  describe('addSenderIdentity', () => {
    it('POSTs the new email to the Flask sender-identities route', async () => {
      const body = { success: true, data: { email: 'new@club.nl', status: 'pending', last_checked: null } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await addSenderIdentity('new@club.nl');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/members/sender-identities'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'new@club.nl' }),
          headers: expect.objectContaining({ Authorization: `Bearer ${mockToken}` }),
        })
      );
      expect(result).toEqual({
        success: true,
        data: { email: 'new@club.nl', status: 'pending', lastChecked: null },
      });
    });
  });

  describe('resendSenderIdentity', () => {
    it('POSTs to the Flask resend route with an empty body (sender resolved server-side)', async () => {
      const body = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await resendSenderIdentity('pending@club.nl');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/members/sender-identities/resend'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      );
      expect(result).toEqual(body);
    });
  });
});
