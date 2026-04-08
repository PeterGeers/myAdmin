/**
 * Authentication Service for AWS Cognito
 * 
 * This service provides utilities for:
 * - JWT token decoding and validation
 * - Role extraction from Cognito groups
 * - Token management
 * - Role validation
 */

import { fetchAuthSession, getCurrentUser, signIn, confirmSignIn, associateWebAuthnCredential, listWebAuthnCredentials, deleteWebAuthnCredential } from 'aws-amplify/auth';

/**
 * JWT Payload structure from Cognito tokens
 */
export interface JWTPayload {
  'cognito:groups'?: string[];
  'custom:tenants'?: string;
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
 * Sign in using passkey (WebAuthn) via Cognito USER_AUTH flow.
 * 
 * Initiates choice-based auth and handles the WEB_AUTHN challenge.
 * The browser will prompt for biometric verification (Face ID / Touch ID / Windows Hello).
 * 
 * @param email - User's email address
 * @returns Sign-in result from Amplify
 */
export async function signInWithPasskey(email: string) {
  // Step 1: Initiate auth with USER_AUTH flow (preferring passkey)
  const result = await signIn({
    username: email,
    options: { authFlowType: 'USER_AUTH' },
  });

  // Step 2: Handle WEB_AUTHN challenge
  // If Cognito returns CONTINUE_SIGN_IN_WITH_FIRST_FACTOR_SELECTION,
  // select WEB_AUTHN to trigger the browser's credential prompt
  if (
    result.nextStep?.signInStep === 'CONTINUE_SIGN_IN_WITH_FIRST_FACTOR_SELECTION'
  ) {
    const confirmResult = await confirmSignIn({
      challengeResponse: 'WEB_AUTHN',
    });
    return confirmResult;
  }

  return result;
}

/**
 * Sign in using email and password via Cognito USER_SRP_AUTH flow.
 * 
 * @param email - User's email address
 * @param password - User's password
 * @returns Sign-in result from Amplify
 */
export async function signInWithPassword(email: string, password: string) {
  const result = await signIn({
    username: email,
    password: password,
    options: { authFlowType: 'USER_SRP_AUTH' },
  });
  return result;
}

/**
 * Wrapper around confirmSignIn for handling WebAuthn challenges.
 * 
 * Use this when the sign-in flow returns a challenge that requires
 * a WebAuthn credential response (e.g. after factor selection).
 * 
 * @param challengeResponse - The WebAuthn challenge response string
 * @returns Confirm sign-in result from Amplify
 */
export async function handleWebAuthnChallenge(challengeResponse: string) {
  const result = await confirmSignIn({ challengeResponse });
  return result;
}

/**
 * Check if the current browser supports passkeys (WebAuthn).
 * 
 * @returns true if PublicKeyCredential API is available
 */
export function isPasskeySupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined'
  );
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

    // Try to get merged roles (global + per-tenant) from API
    try {
      const idToken = tokens.idToken;
      if (idToken) {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:5000';
        const tenant = localStorage.getItem('selectedTenant') || '';
        const headers: Record<string, string> = {
          'Authorization': `Bearer ${idToken}`,
        };
        if (tenant) {
          headers['X-Tenant'] = tenant;
        }
        const resp = await fetch(`${apiUrl}/api/auth/me`, { headers });
        if (resp.ok) {
          const data = await resp.json();
          return data.roles || [];
        }
      }
    } catch {
      // API not available — fall back to JWT
    }

    // Fallback: read from JWT (only has global roles like SysAdmin)
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
    // First try to get email from JWT token
    const tokens = await getCurrentAuthTokens();
    if (tokens?.idToken) {
      const payload = decodeJWTPayload(tokens.idToken);
      if (payload?.email) {
        return payload.email;
      }
    }

    // Fallback to Amplify user object
    const user = await getCurrentUser();
    return user.signInDetails?.loginId || user.username || null;
  } catch (error) {
    console.error('Failed to get current user email:', error);
    return null;
  }
}

/**
 * Get user name from JWT token
 * 
 * @returns User name or null if not available
 */
export async function getCurrentUserName(): Promise<string | null> {
  try {
    const tokens = await getCurrentAuthTokens();
    if (!tokens?.idToken) {
      return null;
    }

    const payload = decodeJWTPayload(tokens.idToken);
    if (!payload) {
      return null;
    }

    // Try to get name from JWT payload
    return (payload as any).name || null;
  } catch (error) {
    console.error('Failed to extract user name:', error);
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

/**
 * Extract user tenants from JWT token
 * 
 * @returns Array of tenant names from custom:tenants claim
 */
export async function getCurrentUserTenants(): Promise<string[]> {
  try {
    const tokens = await getCurrentAuthTokens();
    if (!tokens?.idToken) {
      console.log('[Tenants] No idToken available');
      return [];
    }

    const payload = decodeJWTPayload(tokens.idToken);
    if (!payload) {
      console.log('[Tenants] Failed to decode JWT payload');
      return [];
    }

    // Parse custom:tenants - it's stored as a JSON string array
    let tenantsValue = payload['custom:tenants'];
    console.log('[Tenants] Raw value from JWT:', tenantsValue, 'Type:', typeof tenantsValue);
    
    if (!tenantsValue) {
      console.log('[Tenants] No custom:tenants in JWT');
      return [];
    }

    // If it's already an array, return it
    if (Array.isArray(tenantsValue)) {
      console.log('[Tenants] Already an array:', tenantsValue);
      return tenantsValue;
    }

    // If it's a string, try to parse it
    if (typeof tenantsValue === 'string') {
      console.log('[Tenants] Attempting to parse string:', tenantsValue);
      
      // Handle double-escaped JSON from Cognito (e.g., "[\"GoodwinSolutions\",\"PeterPrive\"]")
      // Check if the string contains escaped quotes
      if (tenantsValue.includes('\\"')) {
        console.log('[Tenants] Detected escaped quotes, unescaping...');
        tenantsValue = tenantsValue.replace(/\\"/g, '"');
        console.log('[Tenants] After unescaping:', tenantsValue);
      }
      
      // Now try to parse the JSON
      try {
        const parsed = JSON.parse(tenantsValue);
        console.log('[Tenants] Parse result:', parsed, 'Type:', typeof parsed);
        
        // Return array or wrap in array
        if (Array.isArray(parsed)) {
          console.log('[Tenants] Final result (array):', parsed);
          return parsed;
        } else {
          console.log('[Tenants] Not an array, wrapping:', [parsed]);
          return [String(parsed)];
        }
      } catch (parseError) {
        // If parsing fails, treat as single tenant
        console.warn('[Tenants] Failed to parse as JSON, treating as single tenant:', parseError);
        return [tenantsValue];
      }
    }

    console.log('[Tenants] Unexpected type, returning empty array');
    return [];
  } catch (error) {
    console.error('[Tenants] Failed to extract user tenants:', error);
    return [];
  }
}

/**
 * Register a new passkey (WebAuthn credential) for the current user.
 * 
 * Amplify v6 handles the full WebAuthn registration flow:
 * 1. Gets credential creation options from Cognito
 * 2. Calls navigator.credentials.create() (browser biometric prompt)
 * 3. Sends attestation back to Cognito
 */
export async function registerPasskey() {
  try {
    await associateWebAuthnCredential();
  } catch (error) {
    console.error('associateWebAuthnCredential error:', error);
    throw error;
  }
}

/**
 * List all registered passkeys for the current user.
 * 
 * @returns Array of WebAuthn credentials
 */
export async function listPasskeys() {
  const result = await listWebAuthnCredentials();
  return result.credentials;
}

/**
 * Delete a registered passkey by credential ID.
 * 
 * @param credentialId - The ID of the credential to remove
 */
export async function deletePasskey(credentialId: string) {
  await deleteWebAuthnCredential({ credentialId });
}
