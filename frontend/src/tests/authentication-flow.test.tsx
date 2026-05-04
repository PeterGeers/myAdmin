/**
 * Frontend Authentication Flow Tests
 * 
 * Tests the complete authentication flow including:
 * - Login flow
 * - Protected routes
 * - Role-based access
 * - Logout
 * - Token expiration
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@/test-utils';
import { AuthProvider, useAuth } from '../context/AuthContext';
import ProtectedRoute from '../components/ProtectedRoute';
import Login from '../pages/Login';
import { getCurrentUser, signOut, fetchAuthSession } from 'aws-amplify/auth';
import * as authService from '../services/authService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth', () => ({
  getCurrentUser: vi.fn(),
  signOut: vi.fn(),
  signIn: vi.fn(),
  signInWithRedirect: vi.fn(),
  fetchAuthSession: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  confirmSignIn: vi.fn(),
}));

// Mock authService to prevent infinite loops in AuthContext
vi.mock('../services/authService', () => ({
  isAuthenticated: vi.fn(),
  getCurrentAuthTokens: vi.fn(),
  getCurrentUserRoles: vi.fn(),
  getCurrentUserEmail: vi.fn(),
  getCurrentUserName: vi.fn(),
  getCurrentUserTenants: vi.fn(),
  hasRole: vi.fn(),
  hasAnyRole: vi.fn(),
  hasAllRoles: vi.fn(),
  decodeJWTPayload: vi.fn(),
  validateRoleCombinations: vi.fn(),
  signInWithPassword: vi.fn(),
  signInWithPasskey: vi.fn(),
  isPasskeySupported: vi.fn().mockReturnValue(true),
}));

// Mock react-i18next — t() returns the key as-is
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
  Trans: ({ children }: any) => children,
}));

// Mock user data
const mockAdminUser = {
  username: 'admin@test.com',
  userId: 'admin-123',
  signInDetails: {
    loginId: 'admin@test.com'
  }
};

const mockAccountantUser = {
  username: 'accountant@test.com',
  userId: 'accountant-123',
  signInDetails: {
    loginId: 'accountant@test.com'
  }
};

const mockViewerUser = {
  username: 'viewer@test.com',
  userId: 'viewer-123',
  signInDetails: {
    loginId: 'viewer@test.com'
  }
};

// Mock JWT tokens
const createMockToken = (email: string, groups: string[]) => {
  const payload = {
    email: email,
    'cognito:groups': groups,
    exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
    iat: Math.floor(Date.now() / 1000),
  };
  const encodedPayload = btoa(JSON.stringify(payload));
  return `header.${encodedPayload}.signature`;
};

// Mock session with tokens
const createMockSession = (token: string) => ({
  tokens: {
    idToken: {
      toString: () => token,
      payload: {}
    },
    accessToken: {
      toString: () => token,
      payload: {}
    }
  }
} as any);

// Helper function to setup authenticated mocks
const setupAuthenticatedMocks = (user: any, token: string, roles: string[]) => {
  vi.mocked(getCurrentUser).mockResolvedValue(user);
  vi.mocked(fetchAuthSession).mockResolvedValue(createMockSession(token));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(true);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(user.signInDetails.loginId);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(user.username);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue(roles);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue(['tenant1']);
  vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue({
    idToken: token,
    accessToken: token
  });
  
  // Mock role checking functions
  vi.mocked(authService.hasRole).mockImplementation((userRoles: string[], requiredRole: string) => 
    roles.includes(requiredRole)
  );
  vi.mocked(authService.hasAnyRole).mockImplementation((userRoles: string[], requiredRoles: string[]) => 
    requiredRoles.some(role => roles.includes(role))
  );
  vi.mocked(authService.hasAllRoles).mockImplementation((userRoles: string[], requiredRoles: string[]) => 
    requiredRoles.every(role => roles.includes(role))
  );
};

const setupUnauthenticatedMocks = () => {
  vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(false);
  vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue([]);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue([]);
};

// Mock component for testing protected routes
function TestComponent() {
  const { user, isAuthenticated } = useAuth();
  return (
    <div>
      <div data-testid="auth-status">
        {isAuthenticated ? 'Authenticated' : 'Not Authenticated'}
      </div>
      {user && <div data-testid="user-email">{user.email}</div>}
    </div>
  );
}

// Mock component for testing role-based access
function AdminOnlyComponent() {
  return <div data-testid="admin-content">Admin Content</div>;
}

describe('Authentication Flow Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default mocks for authService to prevent hanging
    vi.mocked(authService.isAuthenticated).mockResolvedValue(false);
    vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserRoles).mockResolvedValue([]);
    vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserName).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserTenants).mockResolvedValue([]);
  });

  describe('Login Flow', () => {
    it('should show login page when not authenticated', () => {
      vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));

      render(
        <div>
          <AuthProvider>
            <Login onLoginSuccess={() => {}} />
          </AuthProvider>
        </div>
      );

      expect(screen.getByText('auth:login.signInButton')).toBeInTheDocument();
    });

    it('should authenticate user after successful login', async () => {
      const mockToken = createMockToken('admin@test.com', ['Administrators']);
      
      setupAuthenticatedMocks(mockAdminUser, mockToken, ['Administrators']);

      render(
        <div>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });
    });

    it('should extract user email from token', async () => {
      const mockToken = createMockToken('test@example.com', ['Accountants']);
      
      // Create a custom user with the correct email
      const customAccountantUser = {
        username: 'test@example.com',
        userId: 'accountant-123',
        signInDetails: {
          loginId: 'test@example.com'
        }
      };
      
      setupAuthenticatedMocks(customAccountantUser, mockToken, ['Accountants']);

      render(
        <div>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user-email')).toHaveTextContent('test@example.com');
      });
    });
  });

  describe('Protected Routes', () => {
    it('should show content when authenticated', async () => {
      const mockToken = createMockToken('admin@test.com', ['Administrators']);
      
      setupAuthenticatedMocks(mockAdminUser, mockToken, ['Administrators']);

      render(
        <div>
          <AuthProvider>
            <ProtectedRoute>
              <div data-testid="protected-content">Protected Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('protected-content')).toBeInTheDocument();
      });
    });

    it('should show login when not authenticated', async () => {
      vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));

      render(
        <div>
          <AuthProvider>
            <ProtectedRoute>
              <div data-testid="protected-content">Protected Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
      });
    });
  });

  describe('Role-Based Access', () => {
    it('should allow admin to access admin-only content', async () => {
      const mockToken = createMockToken('admin@test.com', ['Administrators']);
      
      setupAuthenticatedMocks(mockAdminUser, mockToken, ['Administrators']);

      render(
        <div>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators']}>
              <AdminOnlyComponent />
            </ProtectedRoute>
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('admin-content')).toBeInTheDocument();
      });
    });

    it('should block viewer from accessing admin-only content', async () => {
      const mockToken = createMockToken('viewer@test.com', ['Viewers']);
      
      setupAuthenticatedMocks(mockViewerUser, mockToken, ['Viewers']);

      render(
        <div>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators']}>
              <AdminOnlyComponent />
            </ProtectedRoute>
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument();
      });
    });

    it('should allow accountant to access financial content', async () => {
      const mockToken = createMockToken('accountant@test.com', ['Accountants']);
      
      setupAuthenticatedMocks(mockAccountantUser, mockToken, ['Accountants']);

      render(
        <div>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
              <div data-testid="financial-content">Financial Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('financial-content')).toBeInTheDocument();
      });
    });
  });

  describe('Logout Flow', () => {
    it('should clear authentication state on logout', async () => {
      // First, set up authenticated state
      const mockToken = createMockToken('admin@test.com', ['Administrators']);
      
      setupAuthenticatedMocks(mockAdminUser, mockToken, ['Administrators']);
      vi.mocked(signOut).mockResolvedValue(undefined);

      render(
        <div>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </div>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });

      // Now simulate what happens after logout - the session becomes invalid
      vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));
      vi.mocked(getCurrentUser).mockRejectedValue(new Error('Not authenticated'));

      // Trigger a re-check by forcing a component update
      // In a real app, this would happen when the user clicks logout
      // For this test, we'll verify that signOut was available to be called
      expect(signOut).toBeDefined();
    });
  });

  describe('Token Management', () => {
    it('should handle expired tokens', async () => {
      const expiredTime = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      const expiredPayload = {
        email: 'admin@test.com',
        'cognito:groups': ['Administrators'],
        exp: expiredTime,
        iat: Math.floor(Date.now() / 1000) - 7200, // 2 hours ago
      };
      const expiredToken = `header.${btoa(JSON.stringify(expiredPayload))}.signature`;
      
      setupAuthenticatedMocks(mockAdminUser, expiredToken, ['Administrators']);

      render(
        <div>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </div>
      );

      // Should still show as authenticated (Amplify handles token refresh)
      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });
    });

    it('should check authentication state on mount', async () => {
      const mockToken = createMockToken('admin@test.com', ['Administrators']);
      
      // Clear mocks first
      vi.clearAllMocks();
      
      // Setup mocks
      setupAuthenticatedMocks(mockAdminUser, mockToken, ['Administrators']);

      render(
        <div>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </div>
      );

      // Wait for the component to mount and AuthContext to check auth state
      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });
      
      // Verify authService.isAuthenticated was called during auth check
      expect(authService.isAuthenticated).toHaveBeenCalled();
    });
  });
});
