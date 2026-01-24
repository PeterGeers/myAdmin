/**
 * Tests for authService - Tenant Extraction
 */

import { decodeJWTPayload } from './authService';

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
});
