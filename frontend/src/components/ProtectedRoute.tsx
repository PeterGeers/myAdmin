/**
 * Protected Route Component
 * 
 * Wraps components to enforce authentication and role-based access control.
 * Redirects to login if not authenticated or to unauthorized page if lacking required roles.
 */

import React, { ReactNode } from 'react';
import { useAuth } from '../context/AuthContext';
import Login from '../pages/Login';
import Unauthorized from '../pages/Unauthorized';

interface ProtectedRouteProps {
  children: ReactNode;
  requiredRoles?: string[];
  onLoginSuccess?: () => void;
}

/**
 * ProtectedRoute Component
 * 
 * Protects routes by checking authentication and role requirements.
 * 
 * @param children - The component to render if authorized
 * @param requiredRoles - Optional array of roles required to access this route
 * @param onLoginSuccess - Optional callback after successful login
 * 
 * @example
 * ```tsx
 * // Protect a route with authentication only
 * <ProtectedRoute>
 *   <Dashboard />
 * </ProtectedRoute>
 * 
 * // Protect a route with specific role requirements
 * <ProtectedRoute requiredRoles={['Administrators']}>
 *   <UserManagement />
 * </ProtectedRoute>
 * 
 * // Protect a route with multiple role options (user needs ANY of these)
 * <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
 *   <FinancialReports />
 * </ProtectedRoute>
 * ```
 */
export default function ProtectedRoute({
  children,
  requiredRoles = [],
  onLoginSuccess
}: ProtectedRouteProps) {
  const { isAuthenticated, loading, hasAnyRole } = useAuth();

  // Show loading state while checking authentication
  if (loading) {
    return null; // Parent component handles loading state
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Login onLoginSuccess={onLoginSuccess} />;
  }

  // Check role requirements if specified
  if (requiredRoles.length > 0 && !hasAnyRole(requiredRoles)) {
    return <Unauthorized requiredRoles={requiredRoles} />;
  }

  // User is authenticated and has required roles
  return <>{children}</>;
}
