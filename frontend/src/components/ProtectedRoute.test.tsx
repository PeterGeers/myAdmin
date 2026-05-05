/**
 * Tests for ProtectedRoute Component
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen } from '@/test-utils';
import '@testing-library/jest-dom';
import ProtectedRoute from './ProtectedRoute';

// Mock the auth context
vi.mock('../context/AuthContext', async () => ({
  ...await vi.importActual('../context/AuthContext'),
  useAuth: vi.fn(),
}));

// Mock the Login and Unauthorized pages
vi.mock('../pages/Login', () => {
  return {
    default: function MockLogin() {
      return <div data-testid="login-page">Login Page</div>;
    },
  };
});

vi.mock('../pages/Unauthorized', () => {
  return {
    default: function MockUnauthorized() {
      return <div data-testid="unauthorized-page">Unauthorized Page</div>;
    },
  };
});

// Mock AWS Amplify
vi.mock('aws-amplify/auth', () => ({
  getCurrentUser: vi.fn(),
  signOut: vi.fn(),
  fetchAuthSession: vi.fn(),
}));

import { useAuth } from '../context/AuthContext';

describe('ProtectedRoute', () => {
  const mockChild = <div data-testid="protected-content">Protected Content</div>;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show loading state when authentication is loading', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      loading: true,
      user: null,
      hasAnyRole: vi.fn(),
    } as any);

    const { container } = render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    // Should render nothing during loading
    expect(container.firstChild).toBeNull();
  });

  it('should show login page when user is not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      loading: false,
      user: null,
      hasAnyRole: vi.fn(),
    } as any);

    render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });

  it('should show protected content when user is authenticated and no roles required', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Administrators'] },
      hasAnyRole: vi.fn(() => true),
    } as any);

    render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('should show protected content when user has required role', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Administrators'] },
      hasAnyRole: vi.fn((roles) => roles.includes('Administrators')),
    } as any);

    render(
      <ProtectedRoute requiredRoles={['Administrators']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('unauthorized-page')).not.toBeInTheDocument();
  });

  it('should show unauthorized page when user lacks required role', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Viewers'] },
      hasAnyRole: vi.fn((roles) => !roles.includes('Administrators')),
    } as any);

    render(
      <ProtectedRoute requiredRoles={['Administrators']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('unauthorized-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });

  it('should show protected content when user has any of the required roles', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Accountants'] },
      hasAnyRole: vi.fn((roles) => roles.includes('Accountants')),
    } as any);

    render(
      <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('unauthorized-page')).not.toBeInTheDocument();
  });
});
