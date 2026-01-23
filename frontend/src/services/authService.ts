/**
 * Authentication Service for AWS Cognito
 * 
 * This service provides utilities for:
 * - JWT token decoding and validation
 * - Role extraction from Cognito groups
 * - Token management
 * - Role validation
 */

import { fetchAuthSession, getCurrentUser } from 'aws-amplify/auth';

/**
 * JWT Payload structure from Cognito tokens
 */
export interface JWTPayload {
  'cognito:groups'?: string[];
  username?: string;
  email?: string;
  sub?: string;
  exp?: number;
  iat?: number;
}

/**
 * Authentication tokens from Amplify session
 */
export interface AuthTokens {
  idToken?: string;
  accessToken?: string;
}

/**
 * Role validation result
 */
export interface RoleValidation {
  isValid: boolean;
  hasPermissions: boolean;
  hasTenants: boolean;
  missingRoles: string[];
}

/**
 * Decode JWT payload from token string
 * 
 * @param token - JWT token string
 * @returns Decoded JWT payload or null if invalid
 */
export function decodeJWTPayload(token: string): JWTPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      console.error('Invalid JWT token format');
      return null;
    }

    // Decode payload (second part of JWT)
    const payload = parts[1];
    
    // Add padding if needed for base64 decoding
    const paddedPayload = payload + '='.repeat((4 - (payload.length % 4)) % 4);
    
    // Decode base64 and parse JSON
    const decodedPayload = JSON.parse(atob(paddedPayload));

    return decodedPayload as JWTPayload;
  } catch (error) {
    console.error('Failed to decode JWT:', error);
    return null;
  }
}

/**
 * Get current authentication tokens from Amplify
 * 
 * @returns Authentication tokens or null if not authenticated
 */
export async function getCurrentAuthTokens(): Promise<AuthTokens | null> {
  try {
    const session = await fetchAuthSession();

    if (!session.tokens) {
      return null;
    }

    return {
      idToken: session.tokens.idToken?.toString(),
      accessToken: session.tokens.accessToken?.toString(),
    };
  } catch (error) {
    console.error('Failed to get auth tokens:', error);
    return null;
  }
}

/**
 * Extract user roles from JWT token
 * 
 * @returns Array of role names from cognito:groups claim
 */
export async function getCurrentUserRoles(): Promise<string[]> {
  try {
    const tokens = await getCurrentAuthTokens();
    if (!tokens?.accessToken) {
      return [];
    }

    const payload = decodeJWTPayload(tokens.accessToken);
    if (!payload) {
      return [];
    }

    return payload['cognito:groups'] || [];
  } catch (error) {
    console.error('Failed to extract user roles:', error);
    return [];
  }
}

/**
 * Validate role combinations according to RBAC rules
 * 
 * Rules:
 * - System roles bypass all requirements
 * - Permission roles require tenant roles (except basic user roles)
 * - Basic user roles (myAdminUsers, myAdminApplicants) don't require tenant roles
 * 
 * @param roles - Array of role names to validate
 * @returns Validation result with details
 */
export function validateRoleCombinations(roles: string[]): RoleValidation {
  // Categorize roles
  const permissionRoles = roles.filter(
    (role) =>
      role.includes('_CRUD') ||
      role.includes('_Read') ||
      role.includes('_Export')
  );

  const tenantRoles = roles.filter((role) => role.startsWith('Tenant_'));
  const systemRoles = roles.filter((role) => role.startsWith('System_'));
  const basicRoles = roles.filter((role) =>
    ['myAdminUsers', 'myAdminApplicants'].includes(role)
  );

  // System roles bypass all requirements
  if (systemRoles.length > 0) {
    return {
      isValid: true,
      hasPermissions: true,
      hasTenants: true,
      missingRoles: [],
    };
  }

  // Basic roles don't need additional permissions
  if (basicRoles.length > 0 && permissionRoles.length === 0) {
    return {
      isValid: true,
      hasPermissions: false,
      hasTenants: true,
      missingRoles: [],
    };
  }

  // Permission roles require tenant roles
  const missingRoles: string[] = [];
  if (permissionRoles.length > 0 && tenantRoles.length === 0) {
    missingRoles.push('Tenant role (Tenant_*)');
  }

  return {
    isValid: missingRoles.length === 0,
    hasPermissions: permissionRoles.length > 0,
    hasTenants: tenantRoles.length > 0,
    missingRoles,
  };
}

/**
 * Check if user has a specific role
 * 
 * @param userRoles - Array of user's roles
 * @param requiredRole - Role to check for
 * @returns True if user has the role
 */
export function hasRole(userRoles: string[], requiredRole: string): boolean {
  return userRoles.includes(requiredRole);
}

/**
 * Check if user has any of the specified roles
 * 
 * @param userRoles - Array of user's roles
 * @param requiredRoles - Array of roles to check for
 * @returns True if user has at least one of the roles
 */
export function hasAnyRole(userRoles: string[], requiredRoles: string[]): boolean {
  return requiredRoles.some((role) => userRoles.includes(role));
}

/**
 * Check if user has all of the specified roles
 * 
 * @param userRoles - Array of user's roles
 * @param requiredRoles - Array of roles to check for
 * @returns True if user has all of the roles
 */
export function hasAllRoles(userRoles: string[], requiredRoles: string[]): boolean {
  return requiredRoles.every((role) => userRoles.includes(role));
}

/**
 * Get user email from current session
 * 
 * @returns User email or null if not authenticated
 */
export async function getCurrentUserEmail(): Promise<string | null> {
  try {
    const user = await getCurrentUser();
    return user.signInDetails?.loginId || user.username || null;
  } catch (error) {
    console.error('Failed to get current user email:', error);
    return null;
  }
}

/**
 * Check if current session is valid
 * 
 * @returns True if user is authenticated with valid tokens
 */
export async function isAuthenticated(): Promise<boolean> {
  try {
    const tokens = await getCurrentAuthTokens();
    if (!tokens?.idToken) {
      return false;
    }

    // Check if token is expired
    const payload = decodeJWTPayload(tokens.idToken);
    if (!payload?.exp) {
      return false;
    }

    const now = Math.floor(Date.now() / 1000);
    return payload.exp > now;
  } catch (error) {
    return false;
  }
}
