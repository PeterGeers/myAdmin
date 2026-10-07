/**
 * Tests for authService - Tenant Extraction
 */

import { vi, afterEach } from 'vitest';
import { decodeJWTPayload, getCurrentUserTenants } from './authService';

// Mock the Amplify auth session so `getCurrentAuthTokens` (called internally by
// `getCurrentUserTenants`) resolves to a token we control, without any network.
const mockFetchAuthSession = vi.fn();
vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: (...args: unknown[]) => mockFetchAuthSession(...args),
  getCurrentUser: vi.fn(),
  signIn: vi.fn(),
  confirmSignIn: vi.fn(),
  associateWebAuthnCredential: vi.fn(),
  listWebAuthnCredentials: vi.fn(),
  deleteWebAuthnCredential: vi.fn(),
}));

/** Build a decodable JWT (`header.<base64 payload>.signature`) carrying `claims`. */
function makeToken(claims: Record<string, unknown>): string {
  const payload = {
    email: 'test@example.com',
    sub: 'test-sub',
    exp: Math.floor(Date.now() / 1000) + 3600,
    ...claims,
  };
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

/** Point the mocked session at a token carrying the given `custom:tenants`. */
function sessionWithTenants(tenantsValue: unknown): void {
  const idToken = makeToken({ 'custom:tenants': tenantsValue });
  mockFetchAuthSession.mockResolvedValue({
    tokens: {
      idToken: { toString: () => idToken },
      accessToken: { toString: () => idToken },
    },
  });
}

describe('authService - Tenant Support', () => {
  describe('decodeJWTPayload', () => {
    it('should decode JWT with custom:tenants attribute', () => {
      // Create a mock JWT token with custom:tenants
      const payload = {
        'cognito:groups': ['Finance_CRUD'],
        'custom:tenants': '["GoodwinSolutions","PeterPrive"]',
        email: 'test@example.com',
        sub: 'test-sub',
        exp: Math.floor(Date.now() / 1000) + 3600
      };

      // Encode payload to base64
      const encodedPayload = btoa(JSON.stringify(payload));
      const mockToken = `header.${encodedPayload}.signature`;

      const decoded = decodeJWTPayload(mockToken);

      expect(decoded).toBeTruthy();
      expect(decoded?.['custom:tenants']).toBe('["GoodwinSolutions","PeterPrive"]');
      expect(decoded?.['cognito:groups']).toEqual(['Finance_CRUD']);
    });

    it('should handle JWT without custom:tenants', () => {
      const payload = {
        'cognito:groups': ['Finance_CRUD'],
        email: 'test@example.com',
        sub: 'test-sub',
        exp: Math.floor(Date.now() / 1000) + 3600
      };

      const encodedPayload = btoa(JSON.stringify(payload));
      const mockToken = `header.${encodedPayload}.signature`;

      const decoded = decodeJWTPayload(mockToken);

      expect(decoded).toBeTruthy();
      expect(decoded?.['custom:tenants']).toBeUndefined();
      expect(decoded?.['cognito:groups']).toEqual(['Finance_CRUD']);
    });

    it('should return null for invalid JWT', () => {
      const decoded = decodeJWTPayload('invalid-token');
      expect(decoded).toBeNull();
    });
  });

  // Findings F-001: a plain single-tenant string (e.g. "h-dcn") is a valid,
  // expected shape — it is NOT JSON and must not log a noisy parse warning on
  // every load. Only a value that LOOKS like JSON is parsed; a malformed
  // JSON-looking value still warns (that IS worth surfacing).
  describe('getCurrentUserTenants — parse + warning behavior (F-001)', () => {
    let warnSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      mockFetchAuthSession.mockReset();
      warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => { });
    });

    afterEach(() => {
      warnSpy.mockRestore();
    });

    it('returns a plain single-tenant string as a one-element array WITHOUT warning', async () => {
      sessionWithTenants('h-dcn');
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual(['h-dcn']);
      // The whole point of F-001: no console.warn for the common single-tenant case.
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('parses a JSON array value into a string array (no warning)', async () => {
      sessionWithTenants('["GoodwinSolutions","PeterPrive"]');
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual(['GoodwinSolutions', 'PeterPrive']);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('unescapes and parses a double-escaped JSON array (no warning)', async () => {
      sessionWithTenants('[\\"A\\",\\"B\\"]');
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual(['A', 'B']);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('WARNS only when a JSON-looking value fails to parse (genuine anomaly)', async () => {
      // Starts with '[' so it is treated as JSON, but is malformed → warns + degrades.
      sessionWithTenants('[not valid json');
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual(['[not valid json']);
      expect(warnSpy).toHaveBeenCalledTimes(1);
    });

    it('returns an array value as-is', async () => {
      sessionWithTenants(['t1', 't2']);
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual(['t1', 't2']);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('returns an empty array when there is no custom:tenants claim', async () => {
      sessionWithTenants(undefined);
      const tenants = await getCurrentUserTenants();
      expect(tenants).toEqual([]);
      expect(warnSpy).not.toHaveBeenCalled();
    });
  });
});
