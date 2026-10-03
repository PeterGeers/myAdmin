/**
 * Authentication Context for myAdmin
 * 
 * Provides authentication state management and utilities throughout the app.
 * Uses AWS Amplify for Cognito integration.
 */

import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';
import { getCurrentUser, signOut } from 'aws-amplify/auth';
import {
  getCurrentUserRoles,
  getCurrentUserEmail,
  getCurrentUserName,
  getCurrentUserTenants,
  isAuthenticated as checkAuthenticated,
  hasRole as checkHasRole,
  hasAnyRole as checkHasAnyRole,
  hasAllRoles as checkHasAllRoles,
  validateRoleCombinations,
  type RoleValidation
} from '../services/authService';

/**
 * User information from Cognito
 */
export interface User {
  username: string;
  email: string | null;
  name: string | null;
  roles: string[];
  tenants: string[];
  sub: string;
}

/**
 * Authentication context value
 */
interface AuthContextValue {
  // User state
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;

  // Authentication actions
  logout: () => Promise<void>;
  refreshUserRoles: () => Promise<void>;
  refreshRolesForTenant: (tenant: string) => Promise<void>;

  // Role checking utilities
  hasRole: (role: string) => boolean;
  hasAnyRole: (roles: string[]) => boolean;
  hasAllRoles: (roles: string[]) => boolean;
  validateRoles: () => RoleValidation;
}

/**
 * Authentication context
 */
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Props for AuthProvider
 */
interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Authentication Provider Component
 * 
 * Wraps the application to provide authentication state and utilities.
 * Automatically checks authentication status on mount and provides
 * methods for login, logout, and role checking.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Out-of-order guard for rapid tenant switches. A monotonically increasing
  // request id records which role re-resolution was started last; the latest
  // requested tenant is tracked alongside it. When a response resolves, its
  // result is applied only if it is still the most recent request — so a late
  // response for a superseded tenant never overwrites a newer one. This mirrors
  // the cancelled-flag + tenant-at-start idiom in useTenantModules; here the
  // guard is internal so out-of-order is safe even without effect cleanup.
  const roleRequestSeq = useRef(0);
  const latestRequestedTenant = useRef<string | null>(null);

  /**
   * Check current authentication state
   * Fetches user info and roles from Cognito
   */
  const checkAuthState = async () => {
    try {
      setLoading(true);

      // Check if user is authenticated
      const authenticated = await checkAuthenticated();
      if (!authenticated) {
        setUser(null);
        return;
      }

      // Get current user info
      const currentUser = await getCurrentUser();
      const email = await getCurrentUserEmail();
      const name = await getCurrentUserName();
      const roles = await getCurrentUserRoles();
      const tenants = await getCurrentUserTenants();

      // Set user state
      setUser({
        username: currentUser.username,
        email: email,
        name: name,
        roles: roles,
        tenants: tenants,
        sub: currentUser.userId
      });
    } catch (error) {
      console.error('Failed to check auth state:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Check authentication state on mount
   */
  useEffect(() => {
    checkAuthState();
  }, []);

  /**
   * Logout user and clear state
   */
  const logout = async () => {
    try {
      await signOut();
      setUser(null);
    } catch (error) {
      console.error('Failed to logout:', error);
      throw error;
    }
  };

  /**
   * Refresh user roles from Cognito
   * Useful after role assignments change
   */
  const refreshUserRoles = async () => {
    await checkAuthState();
  };

  /**
   * Re-resolve ONLY user.roles for an explicitly supplied tenant.
   *
   * Called when the active tenant changes (in-app switch, no reload) so the
   * menu is gated on the newly selected tenant's effective (merged global +
   * per-tenant) roles. Updates user.roles in place — email/name/tenants/sub are
   * left untouched and there is no intermediate empty state, so a still-valid
   * entry never flickers away. getCurrentUserRoles(tenant) sets X-Tenant from
   * the argument, uses a fresh (no-store) body, and falls back to the JWT
   * cognito:groups on failure, so on error we degrade to global roles rather
   * than clearing the set.
   *
   * Out-of-order guard: the tenant and a sequence number are captured at call
   * start; after the await resolves the result is applied only if this is still
   * the latest request (its seq is the current max and its tenant is still the
   * latest requested), so a late response for a superseded tenant is discarded.
   */
  const refreshRolesForTenant = useCallback(async (tenant: string) => {
    const tenantAtStart = tenant;
    const seq = ++roleRequestSeq.current;
    latestRequestedTenant.current = tenantAtStart;

    const roles = await getCurrentUserRoles(tenantAtStart);

    // Ignore results for a tenant we've since switched away from.
    if (seq !== roleRequestSeq.current || latestRequestedTenant.current !== tenantAtStart) {
      return;
    }

    setUser(prev => (prev ? { ...prev, roles } : prev));
  }, []);

  /**
   * Check if user has a specific role
   */
  const hasRole = (role: string): boolean => {
    if (!user || !user.roles) {
      return false;
    }
    return checkHasRole(user.roles, role);
  };

  /**
   * Check if user has any of the specified roles
   */
  const hasAnyRole = (roles: string[]): boolean => {
    if (!user || !user.roles) {
      return false;
    }
    return checkHasAnyRole(user.roles, roles);
  };

  /**
   * Check if user has all of the specified roles
   */
  const hasAllRoles = (roles: string[]): boolean => {
    if (!user || !user.roles) {
      return false;
    }
    return checkHasAllRoles(user.roles, roles);
  };

  /**
   * Validate current user's role combinations
   */
  const validateRoles = (): RoleValidation => {
    if (!user || !user.roles) {
      return {
        isValid: false,
        hasPermissions: false,
        hasTenants: false,
        missingRoles: ['No roles assigned']
      };
    }
    return validateRoleCombinations(user.roles);
  };

  const value: AuthContextValue = {
    user,
    loading,
    isAuthenticated: !!user,
    logout,
    refreshUserRoles,
    refreshRolesForTenant,
    hasRole,
    hasAnyRole,
    hasAllRoles,
    validateRoles
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to use authentication context
 * 
 * @throws Error if used outside of AuthProvider
 * @returns Authentication context value
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { user, isAuthenticated, hasRole, logout } = useAuth();
 *   
 *   if (!isAuthenticated) {
 *     return <div>Please login</div>;
 *   }
 *   
 *   return (
 *     <div>
 *       <p>Welcome {user.email}</p>
 *       {hasRole('Administrators') && <AdminPanel />}
 *       <button onClick={logout}>Logout</button>
 *     </div>
 *   );
 * }
 * ```
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
