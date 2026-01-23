/**
 * Tests for Authentication Service
 */

import {
  decodeJWTPayload,
  validateRoleCombinations,
  hasRole,
  hasAnyRole,
  hasAllRoles,
} from './authService';

describe('authService', () => {
  describe('decodeJWTPayload', () => {
    it('should decode a valid JWT token', () => {
      // Create a mock JWT token with known payload
      const payload = {
        'cognito:groups': ['Administrators'],
        email: 'test@example.com',
        username: 'testuser',
        sub: '12345',
        exp: 1234567890,
        iat: 1234567800,
      };

      // Encode payload to base64
      const encodedPayload = btoa(JSON.stringify(payload));
      const mockToken = `header.${encodedPayload}.signature`;

      const decoded = decodeJWTPayload(mockToken);

      expect(decoded).not.toBeNull();
      expect(decoded?.email).toBe('test@example.com');
      expect(decoded?.username).toBe('testuser');
      expect(decoded?.['cognito:groups']).toEqual(['Administrators']);
    });

    it('should handle JWT token with padding', () => {
      const payload = { email: 'test@example.com' };
      // Create payload that needs padding
      const encodedPayload = btoa(JSON.stringify(payload)).replace(/=/g, '');
      const mockToken = `header.${encodedPayload}.signature`;

      const decoded = decodeJWTPayload(mockToken);

      expect(decoded).not.toBeNull();
      expect(decoded?.email).toBe('test@example.com');
    });

    it('should return null for invalid token format', () => {
      const invalidToken = 'not.a.valid.jwt.token';
      const decoded = decodeJWTPayload(invalidToken);
      expect(decoded).toBeNull();
    });

    it('should return null for malformed token', () => {
      const malformedToken = 'invalid-token';
      const decoded = decodeJWTPayload(malformedToken);
      expect(decoded).toBeNull();
    });

    it('should return null for token with invalid JSON', () => {
      const invalidJson = btoa('not valid json');
      const mockToken = `header.${invalidJson}.signature`;
      const decoded = decodeJWTPayload(mockToken);
      expect(decoded).toBeNull();
    });
  });

  describe('validateRoleCombinations', () => {
    it('should validate system roles bypass all requirements', () => {
      const roles = ['System_CRUD'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(true);
      expect(validation.missingRoles).toEqual([]);
    });

    it('should validate System_User_Management role', () => {
      const roles = ['System_User_Management'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(true);
    });

    it('should validate basic user roles without tenant requirements', () => {
      const roles = ['myAdminUsers'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(false);
      expect(validation.hasTenants).toBe(true);
      expect(validation.missingRoles).toEqual([]);
    });

    it('should validate myAdminApplicants role', () => {
      const roles = ['myAdminApplicants'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(false);
      expect(validation.hasTenants).toBe(true);
    });

    it('should require tenant role for permission roles', () => {
      const roles = ['Finance_CRUD'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(false);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(false);
      expect(validation.missingRoles).toContain('Tenant role (Tenant_*)');
    });

    it('should validate permission role with tenant role', () => {
      const roles = ['Finance_CRUD', 'Tenant_All'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(true);
      expect(validation.missingRoles).toEqual([]);
    });

    it('should validate multiple permission roles with tenant', () => {
      const roles = ['Finance_CRUD', 'STR_Read', 'Tenant_PeterPrive'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(true);
    });

    it('should validate Finance_Read role with tenant', () => {
      const roles = ['Finance_Read', 'Tenant_All'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
    });

    it('should validate Finance_Export role with tenant', () => {
      const roles = ['Finance_Export', 'Tenant_GoodwinSolutions'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
    });

    it('should handle empty roles array', () => {
      const roles: string[] = [];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(false);
      expect(validation.hasTenants).toBe(false);
    });

    it('should handle mixed basic and permission roles', () => {
      const roles = ['myAdminUsers', 'Finance_CRUD', 'Tenant_All'];
      const validation = validateRoleCombinations(roles);

      expect(validation.isValid).toBe(true);
      expect(validation.hasPermissions).toBe(true);
      expect(validation.hasTenants).toBe(true);
    });
  });

  describe('hasRole', () => {
    it('should return true when user has the role', () => {
      const userRoles = ['Administrators', 'Finance_CRUD'];
      expect(hasRole(userRoles, 'Administrators')).toBe(true);
    });

    it('should return false when user does not have the role', () => {
      const userRoles = ['Accountants'];
      expect(hasRole(userRoles, 'Administrators')).toBe(false);
    });

    it('should handle empty roles array', () => {
      const userRoles: string[] = [];
      expect(hasRole(userRoles, 'Administrators')).toBe(false);
    });
  });

  describe('hasAnyRole', () => {
    it('should return true when user has at least one role', () => {
      const userRoles = ['Accountants', 'Finance_Read'];
      const requiredRoles = ['Administrators', 'Accountants'];
      expect(hasAnyRole(userRoles, requiredRoles)).toBe(true);
    });

    it('should return false when user has none of the roles', () => {
      const userRoles = ['Viewers'];
      const requiredRoles = ['Administrators', 'Accountants'];
      expect(hasAnyRole(userRoles, requiredRoles)).toBe(false);
    });

    it('should handle empty required roles', () => {
      const userRoles = ['Administrators'];
      const requiredRoles: string[] = [];
      expect(hasAnyRole(userRoles, requiredRoles)).toBe(false);
    });

    it('should handle empty user roles', () => {
      const userRoles: string[] = [];
      const requiredRoles = ['Administrators'];
      expect(hasAnyRole(userRoles, requiredRoles)).toBe(false);
    });
  });

  describe('hasAllRoles', () => {
    it('should return true when user has all required roles', () => {
      const userRoles = ['Administrators', 'Finance_CRUD', 'Tenant_All'];
      const requiredRoles = ['Administrators', 'Finance_CRUD'];
      expect(hasAllRoles(userRoles, requiredRoles)).toBe(true);
    });

    it('should return false when user is missing some roles', () => {
      const userRoles = ['Administrators'];
      const requiredRoles = ['Administrators', 'Finance_CRUD'];
      expect(hasAllRoles(userRoles, requiredRoles)).toBe(false);
    });

    it('should return true for empty required roles', () => {
      const userRoles = ['Administrators'];
      const requiredRoles: string[] = [];
      expect(hasAllRoles(userRoles, requiredRoles)).toBe(true);
    });

    it('should handle empty user roles', () => {
      const userRoles: string[] = [];
      const requiredRoles = ['Administrators'];
      expect(hasAllRoles(userRoles, requiredRoles)).toBe(false);
    });
  });
});
