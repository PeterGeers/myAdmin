/**
 * Tests for AuthContext
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@/test-utils';
import { AuthProvider, useAuth } from './AuthContext';
import { getCurrentUser, signOut, fetchAuthSession } from 'aws-amplify/auth';
import * as authService from '../services/authService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

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
}));

const mockGetCurrentUser = vi.mocked(getCurrentUser);
const mockSignOut = vi.mocked(signOut);
const mockFetchAuthSession = vi.mocked(fetchAuthSession);

// Mock JWT token creation
const createMockToken = (email: string, groups: string[]) => {
  const payload = {
    email: email,
    'cognito:groups': groups,
    exp: Math.floor(Date.now() / 1000) + 3600,
    iat: Math.floor(Date.now() / 1000),
  };
  const encodedPayload = btoa(JSON.stringify(payload));
  return `header.${encodedPayload}.signature`;
};

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

// Helper functions for setting up mocks
const setupAuthenticatedMocks = (user: any, token: string, roles: string[]) => {
  mockGetCurrentUser.mockResolvedValue(user);
  mockFetchAuthSession.mockResolvedValue(createMockSession(token));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(true);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(user.signInDetails?.loginId || user.username);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(user.username);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue(roles);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue(['tenant1']);
  vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue({
    idToken: token,
    accessToken: token
  });
  vi.mocked(authService.hasRole).mockImplementation((userRoles: string[], requiredRole: string) => 
    roles.includes(requiredRole)
  );
};

const setupUnauthenticatedMocks = () => {
  mockFetchAuthSession.mockRejectedValue(new Error('Not authenticated'));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(false);
  vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue([]);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue([]);
};

// Test component that uses the auth context
function TestComponent() {
  const { user, loading, isAuthenticated, hasRole, logout } = useAuth();

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return <div>Not authenticated</div>;
  }

  return (
    <div>
      <div data-testid="username">{user?.username}</div>
      <div data-testid="email">{user?.email}</div>
      <div data-testid="roles">{user?.roles.join(', ')}</div>
      <div data-testid="has-admin">{hasRole('Administrators') ? 'yes' : 'no'}</div>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe('AuthContext', () => {
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

  it('should throw error when useAuth is used outside AuthProvider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      render(<TestComponent />);
    }).toThrow('useAuth must be used within an AuthProvider');

    consoleSpy.mockRestore();
  });

  it('should show loading state initially', () => {
    setupUnauthenticatedMocks();

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should show not authenticated when user is not logged in', async () => {
    setupUnauthenticatedMocks();

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Not authenticated')).toBeInTheDocument();
    });
  });

  it('should load user data when authenticated', async () => {
    const mockUser = {
      username: 'testuser',
      userId: 'test-user-id',
      signInDetails: {
        loginId: 'test@example.com'
      }
    };
    const mockToken = createMockToken('test@example.com', ['Administrators', 'Finance_CRUD']);
    
    setupAuthenticatedMocks(mockUser, mockToken, ['Administrators', 'Finance_CRUD']);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('username')).toHaveTextContent('testuser');
      expect(screen.getByTestId('email')).toHaveTextContent('test@example.com');
      expect(screen.getByTestId('roles')).toHaveTextContent('Administrators, Finance_CRUD');
      expect(screen.getByTestId('has-admin')).toHaveTextContent('yes');
    });
  });

  it('should handle authentication errors gracefully', async () => {
    mockFetchAuthSession.mockRejectedValue(new Error('Auth error'));
    vi.mocked(authService.isAuthenticated).mockRejectedValue(new Error('Auth error'));

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Not authenticated')).toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });

  it('should handle logout', async () => {
    const mockUser = {
      username: 'testuser',
      userId: 'test-user-id',
      signInDetails: {
        loginId: 'test@example.com'
      }
    };
    const mockToken = createMockToken('test@example.com', ['Administrators']);
    
    setupAuthenticatedMocks(mockUser, mockToken, ['Administrators']);
    mockSignOut.mockResolvedValue();

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('username')).toHaveTextContent('testuser');
    });

    // Click logout button
    const logoutButton = screen.getByText('Logout');
    logoutButton.click();

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalled();
    });
  });

  it('should check roles correctly', async () => {
    const mockUser = {
      username: 'testuser',
      userId: 'test-user-id',
      signInDetails: {
        loginId: 'test@example.com'
      }
    };
    const mockToken = createMockToken('test@example.com', ['Finance_Read', 'Tenant_All']);
    
    setupAuthenticatedMocks(mockUser, mockToken, ['Finance_Read', 'Tenant_All']);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('has-admin')).toHaveTextContent('no');
    });
  });
});
