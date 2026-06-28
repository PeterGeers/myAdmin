/**
 * Unit tests for Login.tsx
 *
 * Tests the authentication login page:
 * - Renders login form with email/password fields
 * - Calls signInWithPassword on form submit
 * - Shows forgot password view
 * - Passkey button visibility
 * - Error handling on auth failure
 *
 * Task 55 of Phase 7: Missing Test Coverage
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import Login from '../pages/Login';
import { render, screen, fireEvent, waitFor } from '@/test-utils';

// Mock authService
const mockSignInWithPassword = vi.fn();
const mockSignInWithPasskey = vi.fn();
const mockIsPasskeySupported = vi.fn();

vi.mock('../services/authService', () => ({
  signInWithPassword: (...args: unknown[]) => mockSignInWithPassword(...args),
  signInWithPasskey: (...args: unknown[]) => mockSignInWithPasskey(...args),
  isPasskeySupported: () => mockIsPasskeySupported(),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock config
vi.mock('../config', () => ({
  buildApiUrl: (path: string) => `http://localhost:5000${path}`,
}));

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsPasskeySupported.mockReturnValue(false);
    mockSignInWithPassword.mockResolvedValue({ isSignedIn: true });
  });

  it('renders login form with email and password fields', () => {
    render(<Login />);

    expect(screen.getByText('auth:login.title')).toBeInTheDocument();
    expect(screen.getByText('auth:login.emailLabel')).toBeInTheDocument();
    expect(screen.getByText('auth:login.passwordLabel')).toBeInTheDocument();
    expect(screen.getByText('auth:login.signInButton')).toBeInTheDocument();
  });

  it('renders email input that accepts user input', () => {
    render(<Login />);

    const emailInput = screen.getByPlaceholderText('user@example.com');
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    expect(emailInput).toHaveValue('test@example.com');
  });

  it('calls signInWithPassword on form submit', async () => {
    const onLoginSuccess = vi.fn();
    render(<Login onLoginSuccess={onLoginSuccess} />);

    const emailInput = screen.getByPlaceholderText('user@example.com');
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });

    // Password input — find by type since the label key is raw
    const form = screen.getByText('auth:login.signInButton').closest('form');
    const pwInput = form?.querySelector('input[type="password"]');
    if (pwInput) {
      fireEvent.change(pwInput, { target: { value: 'mypassword' } });
    }

    fireEvent.click(screen.getByText('auth:login.signInButton'));

    await waitFor(() => {
      expect(mockSignInWithPassword).toHaveBeenCalledWith('test@example.com', 'mypassword');
    });
  });

  it('calls onLoginSuccess when sign-in succeeds', async () => {
    const onLoginSuccess = vi.fn();
    mockSignInWithPassword.mockResolvedValue({ isSignedIn: true });

    render(<Login onLoginSuccess={onLoginSuccess} />);

    const emailInput = screen.getByPlaceholderText('user@example.com');
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });

    const form = screen.getByText('auth:login.signInButton').closest('form');
    const pwInput = form?.querySelector('input[type="password"]');
    if (pwInput) fireEvent.change(pwInput, { target: { value: 'pass123' } });

    fireEvent.click(screen.getByText('auth:login.signInButton'));

    await waitFor(() => {
      expect(onLoginSuccess).toHaveBeenCalled();
    });
  });

  it('shows passkey button when passkeys are supported', () => {
    mockIsPasskeySupported.mockReturnValue(true);
    render(<Login />);

    expect(screen.getByText('auth:login.signInWithPasskey')).toBeInTheDocument();
  });

  it('hides passkey button when passkeys are not supported', () => {
    mockIsPasskeySupported.mockReturnValue(false);
    render(<Login />);

    expect(screen.queryByText('auth:login.signInWithPasskey')).not.toBeInTheDocument();
  });

  it('shows forgot password link', () => {
    render(<Login />);

    expect(screen.getByText('auth:login.resetPassword')).toBeInTheDocument();
  });

  it('switches to forgot password view on link click', () => {
    render(<Login />);

    fireEvent.click(screen.getByText('auth:login.resetPassword'));

    expect(screen.getByText('auth:forgotPassword.title')).toBeInTheDocument();
    expect(screen.getByText('auth:forgotPassword.sendCode')).toBeInTheDocument();
  });

  it('forgot password view has back to login link', () => {
    render(<Login />);

    fireEvent.click(screen.getByText('auth:login.resetPassword'));
    expect(screen.getByText(/auth:forgotPassword.backToLogin/)).toBeInTheDocument();
  });

  it('shows secure login info alert', () => {
    render(<Login />);

    expect(screen.getByText('auth:login.secureLoginInfo')).toBeInTheDocument();
  });
});
