/**
 * Tests for AuthContext
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import { getCurrentUser, signOut } from 'aws-amplify/auth';
import * as authService from '../services/authService';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

const mockGetCurrentUser = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const mockSignOut = signOut as jest.MockedFunction<typeof signOut>;

// Spy on authService functions but use real implementations
const getCurrentUserRolesSpy = jest.spyOn(authService, 'getCurrentUserRoles');
const getCurrentUserEmailSpy = jest.spyOn(authService, 'getCurrentUserEmail');
const isAuthenticatedSpy = jest.spyOn(authService, 'isAuthenticated');

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
    isAuthenticatedSpy.mockResolvedValue(false);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should show not authenticated when user is not logged in', async () => {
    isAuthenticatedSpy.mockResolvedValue(false);

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
    isAuthenticatedSpy.mockResolvedValue(true);
    mockGetCurrentUser.mockResolvedValue({
      username: 'testuser',
      userId: 'test-user-id'
    } as any);
    getCurrentUserEmailSpy.mockResolvedValue('test@example.com');
    getCurrentUserRolesSpy.mockResolvedValue(['Administrators', 'Finance_CRUD']);

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
    isAuthenticatedSpy.mockRejectedValue(new Error('Auth error'));

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
    isAuthenticatedSpy.mockResolvedValue(true);
    mockGetCurrentUser.mockResolvedValue({
      username: 'testuser',
      userId: 'test-user-id'
    } as any);
    getCurrentUserEmailSpy.mockResolvedValue('test@example.com');
    getCurrentUserRolesSpy.mockResolvedValue(['Administrators']);
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
    isAuthenticatedSpy.mockResolvedValue(true);
    mockGetCurrentUser.mockResolvedValue({
      username: 'testuser',
      userId: 'test-user-id'
    } as any);
    getCurrentUserEmailSpy.mockResolvedValue('test@example.com');
    getCurrentUserRolesSpy.mockResolvedValue(['Finance_Read', 'Tenant_All']);

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
