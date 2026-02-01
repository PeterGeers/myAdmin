/**
 * Tests for ProtectedRoute Component
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProtectedRoute from './ProtectedRoute';

// Mock the auth context
jest.mock('../context/AuthContext', () => ({
  ...jest.requireActual('../context/AuthContext'),
  useAuth: jest.fn(),
}));

// Mock the Login and Unauthorized pages
jest.mock('../pages/Login', () => {
  return function MockLogin() {
    return <div data-testid="login-page">Login Page</div>;
  };
});

jest.mock('../pages/Unauthorized', () => {
  return function MockUnauthorized() {
    return <div data-testid="unauthorized-page">Unauthorized Page</div>;
  };
});

// Mock AWS Amplify
jest.mock('aws-amplify/auth', () => ({
  getCurrentUser: jest.fn(),
  signOut: jest.fn(),
  fetchAuthSession: jest.fn(),
}));

const { useAuth } = require('../context/AuthContext');

describe('ProtectedRoute', () => {
  const mockChild = <div data-testid="protected-content">Protected Content</div>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should show loading state when authentication is loading', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: true,
      user: null,
      hasAnyRole: jest.fn(),
    });

    const { container } = render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    // Should render nothing during loading
    expect(container.firstChild).toBeNull();
  });

  it('should show login page when user is not authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: false,
      user: null,
      hasAnyRole: jest.fn(),
    });

    render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });

  it('should show protected content when user is authenticated and no roles required', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Administrators'] },
      hasAnyRole: jest.fn(() => true),
    });

    render(
      <ProtectedRoute>{mockChild}</ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('should show protected content when user has required role', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Administrators'] },
      hasAnyRole: jest.fn((roles) => roles.includes('Administrators')),
    });

    render(
      <ProtectedRoute requiredRoles={['Administrators']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('unauthorized-page')).not.toBeInTheDocument();
  });

  it('should show unauthorized page when user lacks required role', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Viewers'] },
      hasAnyRole: jest.fn((roles) => !roles.includes('Administrators')),
    });

    render(
      <ProtectedRoute requiredRoles={['Administrators']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('unauthorized-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });

  it('should show protected content when user has any of the required roles', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
      user: { email: 'test@example.com', roles: ['Accountants'] },
      hasAnyRole: jest.fn((roles) => roles.includes('Accountants')),
    });

    render(
      <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
        {mockChild}
      </ProtectedRoute>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByTestId('unauthorized-page')).not.toBeInTheDocument();
  });
});
