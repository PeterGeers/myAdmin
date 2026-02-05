/**
 * Tests for AuthContext
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import { getCurrentUser, signOut, fetchAuthSession } from 'aws-amplify/auth';
import * as authService from '../services/authService';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

// Mock authService to prevent infinite loops in AuthContext
jest.mock('../services/authService', () => ({
  isAuthenticated: jest.fn(),
  getCurrentAuthTokens: jest.fn(),
  getCurrentUserRoles: jest.fn(),
  getCurrentUserEmail: jest.fn(),
  getCurrentUserName: jest.fn(),
  getCurrentUserTenants: jest.fn(),
  hasRole: jest.fn(),
  hasAnyRole: jest.fn(),
  hasAllRoles: jest.fn(),
}));

const mockGetCurrentUser = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const mockSignOut = signOut as jest.MockedFunction<typeof signOut>;
const mockFetchAuthSession = fetchAuthSession as jest.MockedFunction<typeof fetchAuthSession>;

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
  (authService.isAuthenticated as jest.Mock).mockResolvedValue(true);
  (authService.getCurrentUserEmail as jest.Mock).mockResolvedValue(user.signInDetails?.loginId || user.username);
  (authService.getCurrentUserName as jest.Mock).mockResolvedValue(user.username);
  (authService.getCurrentUserRoles as jest.Mock).mockResolvedValue(roles);
  (authService.getCurrentUserTenants as jest.Mock).mockResolvedValue(['tenant1']);
  (authService.getCurrentAuthTokens as jest.Mock).mockResolvedValue({
    idToken: token,
    accessToken: token
  });
  (authService.hasRole as jest.Mock).mockImplementation((userRoles: string[], requiredRole: string) => 
    roles.includes(requiredRole)
  );
};

const setupUnauthenticatedMocks = () => {
  mockFetchAuthSession.mockRejectedValue(new Error('Not authenticated'));
  (authService.isAuthenticated as jest.Mock).mockResolvedValue(false);
  (authService.getCurrentAuthTokens as jest.Mock).mockResolvedValue(null);
  (authService.getCurrentUserRoles as jest.Mock).mockResolvedValue([]);
  (authService.getCurrentUserEmail as jest.Mock).mockResolvedValue(null);
  (authService.getCurrentUserName as jest.Mock).mockResolvedValue(null);
  (authService.getCurrentUserTenants as jest.Mock).mockResolvedValue([]);
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
    jest.clearAllMocks();
    
    // Setup default mocks for authService to prevent hanging
    (authService.isAuthenticated as jest.Mock).mockResolvedValue(false);
    (authService.getCurrentAuthTokens as jest.Mock).mockResolvedValue(null);
    (authService.getCurrentUserRoles as jest.Mock).mockResolvedValue([]);
    (authService.getCurrentUserEmail as jest.Mock).mockResolvedValue(null);
    (authService.getCurrentUserName as jest.Mock).mockResolvedValue(null);
    (authService.getCurrentUserTenants as jest.Mock).mockResolvedValue([]);
  });

  it('should throw error when useAuth is used outside AuthProvider', () => {
    // Suppress console.error for this test
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

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
    (authService.isAuthenticated as jest.Mock).mockRejectedValue(new Error('Auth error'));

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

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
