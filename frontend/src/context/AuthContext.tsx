/**
 * Authentication Context for myAdmin
 * 
 * Provides authentication state management and utilities throughout the app.
 * Uses AWS Amplify for Cognito integration.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { getCurrentUser, signOut } from 'aws-amplify/auth';
import {
  getCurrentUserRoles,
  getCurrentUserEmail,
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
      const roles = await getCurrentUserRoles();
      const tenants = await getCurrentUserTenants();

      // Set user state
      setUser({
        username: currentUser.username,
        email: email,
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
