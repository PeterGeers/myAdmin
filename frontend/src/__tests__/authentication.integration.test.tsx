/**
 * Integration Tests for Frontend Authentication
 * 
 * Tests the complete authentication flow including:
 * - Login flow
 * - Protected routes
 * - Role-based access control
 * - Logout functionality
 * - Token expiration handling
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../context/AuthContext';

// Import mocked functions
import { getCurrentUser, signOut, signIn, fetchAuthSession } from 'aws-amplify/auth';
import * as authService from '../services/authService';

// Import components after mocks
import ProtectedRoute from '../components/ProtectedRoute';
import Login from '../pages/Login';
import Unauthorized from '../pages/Unauthorized';

// Mock AWS Amplify auth functions
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
  getCurrentAuthTokens: vi.fn(),
  getCurrentUserRoles: vi.fn(),
  getCurrentUserEmail: vi.fn(),
  getCurrentUserName: vi.fn(),
  getCurrentUserTenants: vi.fn(),
  isAuthenticated: vi.fn(),
  hasRole: vi.fn(),
  hasAnyRole: vi.fn(),
  hasAllRoles: vi.fn(),
  decodeJWTPayload: vi.fn(),
  validateRoleCombinations: vi.fn(),
  signInWithPassword: vi.fn(),
  signInWithPasskey: vi.fn(),
  isPasskeySupported: vi.fn().mockReturnValue(true),
}));

// Mock Chakra UI components to avoid dependency issues
vi.mock('@chakra-ui/react', () => ({
  ChakraProvider: ({ children }: any) => <div>{children}</div>,
  Box: ({ children, as: As, onSubmit, ...props }: any) => As === 'form' ? <form onSubmit={onSubmit} {...props}>{children}</form> : <div {...props}>{children}</div>,
  VStack: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  HStack: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h1 {...props}>{children}</h1>,
  Text: ({ children, ...props }: any) => <p {...props}>{children}</p>,
  Button: ({ children, onClick, type, isLoading, loadingText, isDisabled, ...props }: any) => <button onClick={onClick} type={type} disabled={isDisabled || isLoading} {...props}>{isLoading ? loadingText : children}</button>,
  Image: (props: any) => <img alt="" {...props} />,
  Container: ({ children }: any) => <div>{children}</div>,
  Divider: () => <hr />,
  Link: ({ children, onClick, ...props }: any) => <a onClick={onClick} {...props}>{children}</a>,
  Alert: ({ children }: any) => <div role="alert">{children}</div>,
  AlertIcon: () => <span>ℹ️</span>,
  AlertDescription: ({ children }: any) => <div>{children}</div>,
  CloseButton: ({ onClick }: any) => <button onClick={onClick}>×</button>,
  Badge: ({ children }: any) => <span>{children}</span>,
  Icon: ({ as }: any) => <span>{as?.name || 'icon'}</span>,
  List: ({ children }: any) => <ul>{children}</ul>,
  ListItem: ({ children }: any) => <li>{children}</li>,
  ListIcon: () => <span>✓</span>,
  FormControl: ({ children }: any) => <div>{children}</div>,
  FormLabel: ({ children }: any) => <label>{children}</label>,
  Input: ({ value, onChange, type, placeholder, disabled, ...props }: any) => <input type={type} value={value} onChange={onChange} placeholder={placeholder} disabled={disabled} aria-label={placeholder} />,
  InputGroup: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  InputRightElement: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  IconButton: ({ 'aria-label': ariaLabel, onClick, icon, ...props }: any) => (
    <button aria-label={ariaLabel} onClick={onClick}>{icon || 'icon-btn'}</button>
  ),
  useToast: () => vi.fn(),
}));

vi.mock('@chakra-ui/icons', () => ({
  ViewIcon: () => <span>👁</span>,
  ViewOffIcon: () => <span>👁‍🗨</span>,
  LockIcon: { name: 'LockIcon' },
  WarningIcon: { name: 'WarningIcon' },
  CheckCircleIcon: { name: 'CheckCircleIcon' },
}));

// Mock react-i18next — t() returns the key as-is
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
  Trans: ({ children }: any) => children,
}));

// Helper to wrap components with providers
const renderWithProviders = (ui: React.ReactElement) => {
  return render(
    <AuthProvider>
      {ui}
    </AuthProvider>
  );
};

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
const createMockToken = (groups: string[]) => {
  const payload = {
    'cognito:groups': groups,
    exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
    iat: Math.floor(Date.now() / 1000),
  };
  const encodedPayload = btoa(JSON.stringify(payload));
  return `header.${encodedPayload}.signature`;
};

const mockAdminToken = createMockToken(['Administrators']);
const mockAccountantToken = createMockToken(['Accountants']);
const mockViewerToken = createMockToken(['Viewers']);

// Mock session with tokens
const createMockSession = (token: string) => ({
  tokens: {
    idToken: {
      toString: () => token
    },
    accessToken: {
      toString: () => token
    }
  }
});

// Helper to setup authenticated state mocks
const setupAuthenticatedMocks = (user: any, token: string, roles: string[]) => {
  vi.mocked(getCurrentUser).mockResolvedValue(user);
  vi.mocked(fetchAuthSession).mockResolvedValue(createMockSession(token));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(true);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(user.signInDetails.loginId);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(user.username);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue(roles);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue(['tenant1']);
  
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

// Helper to setup unauthenticated state mocks
const setupUnauthenticatedMocks = () => {
  vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));
  vi.mocked(authService.isAuthenticated).mockResolvedValue(false);
  vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserRoles).mockResolvedValue([]);
  vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserName).mockResolvedValue(null);
  vi.mocked(authService.getCurrentUserTenants).mockResolvedValue([]);
};

describe('Authentication Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Re-set isPasskeySupported after clearAllMocks resets it
    vi.mocked(authService.isPasskeySupported).mockReturnValue(true);
    
    // Setup default mocks for authService to prevent hanging
    vi.mocked(authService.isAuthenticated).mockResolvedValue(false);
    vi.mocked(authService.getCurrentAuthTokens).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserRoles).mockResolvedValue([]);
    vi.mocked(authService.getCurrentUserEmail).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserName).mockResolvedValue(null);
    vi.mocked(authService.getCurrentUserTenants).mockResolvedValue([]);
  });

  describe('Login Flow', () => {
    it('should show login page with email and password fields', async () => {
      setupUnauthenticatedMocks();

      renderWithProviders(<Login />);

      await waitFor(() => {
        expect(screen.getByText('auth:login.title')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('user@example.com')).toBeInTheDocument();
        expect(screen.getByText('auth:login.signInButton')).toBeInTheDocument();
      });
    });

    it('should show passkey button when WebAuthn is supported', async () => {
      setupUnauthenticatedMocks();

      renderWithProviders(<Login />);

      await waitFor(() => {
        expect(screen.getByText('auth:login.signInWithPasskey')).toBeInTheDocument();
      });
    });

    it('should call signInWithPassword on form submit', async () => {
      setupUnauthenticatedMocks();
      vi.mocked(authService.signInWithPassword).mockResolvedValue({ isSignedIn: true });

      renderWithProviders(<Login onLoginSuccess={vi.fn()} />);

      const emailInput = screen.getByPlaceholderText('user@example.com');
      await userEvent.type(emailInput, 'test@example.com');

      const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement;
      await userEvent.type(passwordInput, 'password123');

      const signInButton = screen.getByText('auth:login.signInButton');
      await userEvent.click(signInButton);

      await waitFor(() => {
        expect(authService.signInWithPassword).toHaveBeenCalledWith('test@example.com', 'password123');
      });
    });

    it('should call signInWithPasskey when passkey button clicked', async () => {
      setupUnauthenticatedMocks();
      vi.mocked(authService.signInWithPasskey).mockResolvedValue({ isSignedIn: true });

      renderWithProviders(<Login onLoginSuccess={vi.fn()} />);

      const emailInput = screen.getByPlaceholderText('user@example.com');
      await userEvent.type(emailInput, 'test@example.com');

      const passkeyButton = screen.getByText('auth:login.signInWithPasskey');
      await userEvent.click(passkeyButton);

      await waitFor(() => {
        expect(authService.signInWithPasskey).toHaveBeenCalledWith('test@example.com');
      });
    });

    it('should handle password login errors gracefully', async () => {
      setupUnauthenticatedMocks();
      vi.mocked(authService.signInWithPassword).mockRejectedValue({ name: 'NotAuthorizedException' });

      renderWithProviders(<Login />);

      const emailInput = screen.getByPlaceholderText('user@example.com');
      await userEvent.type(emailInput, 'test@example.com');

      const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement;
      await userEvent.type(passwordInput, 'wrongpassword');

      const signInButton = screen.getByText('auth:login.signInButton');
      await userEvent.click(signInButton);

      await waitFor(() => {
        expect(authService.signInWithPassword).toHaveBeenCalled();
      });
    });

    it('should handle passkey login errors gracefully', async () => {
      setupUnauthenticatedMocks();
      vi.mocked(authService.signInWithPasskey).mockRejectedValue({ name: 'NotAuthorizedException' });

      renderWithProviders(<Login />);

      const emailInput = screen.getByPlaceholderText('user@example.com');
      await userEvent.type(emailInput, 'test@example.com');

      const passkeyButton = screen.getByText('auth:login.signInWithPasskey');
      await userEvent.click(passkeyButton);

      await waitFor(() => {
        expect(authService.signInWithPasskey).toHaveBeenCalled();
      });
    });

    it('should show forgot password view when link clicked', async () => {
      setupUnauthenticatedMocks();

      renderWithProviders(<Login />);

      const resetLink = screen.getByText('auth:login.resetPassword');
      await userEvent.click(resetLink);

      await waitFor(() => {
        expect(screen.getByText('auth:forgotPassword.title')).toBeInTheDocument();
        expect(screen.getByText('auth:forgotPassword.sendCode')).toBeInTheDocument();
      });
    });
  });

  describe('Protected Routes', () => {
    it('should show login page for unauthenticated users', async () => {
      setupUnauthenticatedMocks();

      const TestComponent = () => <div>Protected Content</div>;

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('auth:login.title')).toBeInTheDocument();
        expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
      });
    });

    it('should show protected content for authenticated users', async () => {
      setupAuthenticatedMocks(mockAdminUser, mockAdminToken, ['Administrators']);

      const TestComponent = () => <div>Protected Content</div>;

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument();
      });
    });

    it('should redirect to login after logout', async () => {
      setupAuthenticatedMocks(mockAdminUser, mockAdminToken, ['Administrators']);
      vi.mocked(signOut).mockResolvedValue(undefined);

      const TestComponent = () => {
        const { logout } = useAuth();
        return (
          <div>
            <div>Protected Content</div>
            <button onClick={logout}>Logout</button>
          </div>
        );
      };

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument();
      });

      // Simulate logout
      vi.mocked(fetchAuthSession).mockRejectedValue(new Error('Not authenticated'));
      const logoutButton = screen.getByText('Logout');
      await userEvent.click(logoutButton);

      await waitFor(() => {
        expect(signOut).toHaveBeenCalled();
      });
    });
  });

  describe('Role-Based Access Control', () => {
    it('should allow admin access to all pages', async () => {
      setupAuthenticatedMocks(mockAdminUser, mockAdminToken, ['Administrators']);

      const AdminComponent = () => <div>Admin Only Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators']}>
          <AdminComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Admin Only Content')).toBeInTheDocument();
      });
    });

    it('should allow accountant access to financial pages', async () => {
      setupAuthenticatedMocks(mockAccountantUser, mockAccountantToken, ['Accountants']);

      const FinancialComponent = () => <div>Financial Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators', 'Accountants']}>
          <FinancialComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Financial Content')).toBeInTheDocument();
      });
    });

    it('should allow viewer access to reports only', async () => {
      setupAuthenticatedMocks(mockViewerUser, mockViewerToken, ['Viewers']);

      const ReportsComponent = () => <div>Reports Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators', 'Accountants', 'Viewers']}>
          <ReportsComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Reports Content')).toBeInTheDocument();
      });
    });

    it('should block viewer from accessing admin pages', async () => {
      setupAuthenticatedMocks(mockViewerUser, mockViewerToken, ['Viewers']);

      const AdminComponent = () => <div>Admin Only Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators']}>
          <AdminComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('auth:unauthorized.title')).toBeInTheDocument();
        expect(screen.queryByText('Admin Only Content')).not.toBeInTheDocument();
      });
    });

    it('should show unauthorized page with role information', async () => {
      setupAuthenticatedMocks(mockViewerUser, mockViewerToken, ['Viewers']);

      const AdminComponent = () => <div>Admin Only Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators']}>
          <AdminComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('auth:unauthorized.title')).toBeInTheDocument();
        expect(screen.getByText('auth:unauthorized.yourRoles')).toBeInTheDocument();
        expect(screen.getByText('auth:unauthorized.requiredRoles')).toBeInTheDocument();
      });
    });

    it('should allow access when user has any of the required roles', async () => {
      setupAuthenticatedMocks(mockAccountantUser, mockAccountantToken, ['Accountants']);

      const MultiRoleComponent = () => <div>Multi Role Content</div>;

      renderWithProviders(
        <ProtectedRoute requiredRoles={['Administrators', 'Accountants', 'Viewers']}>
          <MultiRoleComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Multi Role Content')).toBeInTheDocument();
      });
    });
  });

  describe('Logout Functionality', () => {
    it('should successfully logout user', async () => {
      setupAuthenticatedMocks(mockAdminUser, mockAdminToken, ['Administrators']);
      vi.mocked(signOut).mockResolvedValue(undefined);

      renderWithProviders(<Unauthorized requiredRoles={['Administrators']} />);

      await waitFor(() => {
        expect(screen.getByText('auth:unauthorized.title')).toBeInTheDocument();
      });

      const logoutButton = screen.getByText('common:buttons.cancel');
      await userEvent.click(logoutButton);

      await waitFor(() => {
        expect(signOut).toHaveBeenCalled();
      });
    });
  });

  describe('Token Expiration', () => {
    it('should detect expired tokens', async () => {
      const expiredPayload = {
        'cognito:groups': ['Administrators'],
        exp: Math.floor(Date.now() / 1000) - 3600, // 1 hour ago
        iat: Math.floor(Date.now() / 1000) - 7200,
      };
      const encodedPayload = btoa(JSON.stringify(expiredPayload));
      const expiredToken = `header.${encodedPayload}.signature`;

      vi.mocked(getCurrentUser).mockResolvedValue(mockAdminUser);
      vi.mocked(fetchAuthSession).mockResolvedValue(createMockSession(expiredToken));
      // For expired tokens, isAuthenticated should return false
      vi.mocked(authService.isAuthenticated).mockResolvedValue(false);

      const TestComponent = () => <div>Protected Content</div>;

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      // Should redirect to login due to expired token
      await waitFor(() => {
        expect(screen.getByText('auth:login.title')).toBeInTheDocument();
      });
    });

    it('should accept valid tokens', async () => {
      const validPayload = {
        'cognito:groups': ['Administrators'],
        exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
        iat: Math.floor(Date.now() / 1000),
      };
      const encodedPayload = btoa(JSON.stringify(validPayload));
      const validToken = `header.${encodedPayload}.signature`;

      setupAuthenticatedMocks(mockAdminUser, validToken, ['Administrators']);

      const TestComponent = () => <div>Protected Content</div>;

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument();
      });
    });
  });

  describe('User Experience', () => {
    it('should show loading state while checking authentication', async () => {
      vi.mocked(getCurrentUser).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );
      vi.mocked(fetchAuthSession).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );
      setupUnauthenticatedMocks();

      const TestComponent = () => <div>Protected Content</div>;

      renderWithProviders(
        <ProtectedRoute>
          <TestComponent />
        </ProtectedRoute>
      );

      // Should not show content or login page while loading
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
      expect(screen.queryByText('auth:login.title')).not.toBeInTheDocument();
    });

    it('should display user email in unauthorized page', async () => {
      setupAuthenticatedMocks(mockViewerUser, mockViewerToken, ['Viewers']);

      renderWithProviders(<Unauthorized requiredRoles={['Administrators']} />);

      await waitFor(() => {
        expect(screen.getByText('viewer@test.com')).toBeInTheDocument();
      });
    });

    it('should show forgot password link on login page', async () => {
      setupUnauthenticatedMocks();

      renderWithProviders(<Login />);

      await waitFor(() => {
        expect(screen.getByText('auth:login.forgotPassword')).toBeInTheDocument();
        expect(screen.getByText('auth:login.resetPassword')).toBeInTheDocument();
      });
    });

    it('should show go back button on unauthorized page', async () => {
      setupAuthenticatedMocks(mockViewerUser, mockViewerToken, ['Viewers']);

      renderWithProviders(<Unauthorized requiredRoles={['Administrators']} />);

      await waitFor(() => {
        expect(screen.getByText('auth:unauthorized.goBack')).toBeInTheDocument();
      });
    });
  });
});
