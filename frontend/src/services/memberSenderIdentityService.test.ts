/**
 * Member sender-identity service - Unit Tests (R0, design §6.2).
 *
 * Verifies each function hits the correct Members route + method with the
 * authenticated headers, mirroring the taxRateService test pattern.
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
    it('GETs the sender-identities list', async () => {
      const body = {
        success: true,
        data: { identities: [{ email: 'a@club.nl', status: 'verified', lastChecked: null }] },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await getSenderIdentities();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/members/sender-identities'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Authorization: `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(body);
    });
  });

  describe('addSenderIdentity', () => {
    it('POSTs the new email to the sender-identities route', async () => {
      const body = { success: true, data: { email: 'new@club.nl', status: 'pending', lastChecked: null } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await addSenderIdentity('new@club.nl');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/members/sender-identities'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'new@club.nl' }),
          headers: expect.objectContaining({ Authorization: `Bearer ${mockToken}` }),
        })
      );
      expect(result).toEqual(body);
    });
  });

  describe('resendSenderIdentity', () => {
    it('POSTs to the resend route with the email', async () => {
      const body = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body }));

      const result = await resendSenderIdentity('pending@club.nl');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/members/sender-identities/resend'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'pending@club.nl' }),
        })
      );
      expect(result).toEqual(body);
    });
  });
});
