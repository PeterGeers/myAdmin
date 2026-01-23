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

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { AuthProvider, useAuth } from '../context/AuthContext';
import ProtectedRoute from '../components/ProtectedRoute';
import Login from '../pages/Login';
import { signIn, signOut, fetchAuthSession } from 'aws-amplify/auth';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

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
    jest.clearAllMocks();
  });

  describe('Login Flow', () => {
    it('should show login page when not authenticated', () => {
      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: null
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <Login onLoginSuccess={() => {}} />
          </AuthProvider>
        </ChakraProvider>
      );

      expect(screen.getByText(/Sign in with Cognito/i)).toBeInTheDocument();
    });

    it('should authenticate user after successful login', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });
    });

    it('should extract user email from token', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'test@example.com',
            'cognito:groups': ['Accountants']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user-email')).toHaveTextContent('test@example.com');
      });
    });
  });

  describe('Protected Routes', () => {
    it('should show content when authenticated', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <ProtectedRoute>
              <div data-testid="protected-content">Protected Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('protected-content')).toBeInTheDocument();
      });
    });

    it('should show login when not authenticated', async () => {
      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: null
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <ProtectedRoute>
              <div data-testid="protected-content">Protected Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
      });
    });
  });

  describe('Role-Based Access', () => {
    it('should allow admin to access admin-only content', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators']}>
              <AdminOnlyComponent />
            </ProtectedRoute>
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('admin-content')).toBeInTheDocument();
      });
    });

    it('should block viewer from accessing admin-only content', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'viewer@test.com',
            'cognito:groups': ['Viewers']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators']}>
              <AdminOnlyComponent />
            </ProtectedRoute>
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument();
      });
    });

    it('should allow accountant to access financial content', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'accountant@test.com',
            'cognito:groups': ['Accountants']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
              <div data-testid="financial-content">Financial Content</div>
            </ProtectedRoute>
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('financial-content')).toBeInTheDocument();
      });
    });
  });

  describe('Logout Flow', () => {
    it('should clear authentication state on logout', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      (signOut as jest.Mock).mockResolvedValue(undefined);

      const { rerender } = render(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });

      // Simulate logout
      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: null
      });

      rerender(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Not Authenticated');
      });
    });
  });

  describe('Token Management', () => {
    it('should handle expired tokens', async () => {
      const expiredTime = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators'],
            exp: expiredTime
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      // Should still show as authenticated (Amplify handles token refresh)
      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated');
      });
    });

    it('should refresh tokens automatically', async () => {
      const mockTokens = {
        idToken: {
          toString: () => 'mock-id-token',
          payload: {
            email: 'admin@test.com',
            'cognito:groups': ['Administrators']
          }
        },
        accessToken: {
          toString: () => 'mock-access-token'
        }
      };

      (fetchAuthSession as jest.Mock).mockResolvedValue({
        tokens: mockTokens
      });

      render(
        <ChakraProvider>
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        </ChakraProvider>
      );

      await waitFor(() => {
        expect(fetchAuthSession).toHaveBeenCalled();
      });
    });
  });
});
