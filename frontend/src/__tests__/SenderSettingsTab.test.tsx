/**
 * Unit Tests for SenderSettingsTab Component
 *
 * Tests rendering of verification status states, resend button cooldown,
 * email update form validation, and API error handling with toast display.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@/test-utils';
import SenderSettingsTab from '../components/TenantAdmin/SenderSettingsTab';

// Mock the verificationApi module
vi.mock('../services/verificationApi', () => ({
  getVerificationStatus: vi.fn(),
  resendVerification: vi.fn(),
  updateSenderEmail: vi.fn(),
}));

// Import mocked functions for test control
import { getVerificationStatus, resendVerification, updateSenderEmail } from '../services/verificationApi';

// Mock useToast
const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@chakra-ui/react')>();
  return {
    ...actual,
    useToast: () => mockToast,
  };
});

// Helper to create mock verification data
function createMockStatus(status: 'pending' | 'verified' | 'failed' | 'expired') {
  return {
    success: true,
    data: {
      email: 'tenant@example.com',
      status,
      lastChecked: '2025-01-15T10:30:00Z',
      fallbackSender: 'myAdmin <support@jabaki.nl>',
    },
  };
}

describe('SenderSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Requirement 7.1 & 7.2: Display email and status badge for each state
  // =========================================================================

  describe('Status rendering (Requirements 7.1, 7.2)', () => {
    it('renders pending status with yellow badge and info message', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('pending'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getAllByText('tenant@example.com').length).toBeGreaterThan(0);
      });

      // Badge with "Pending" label
      expect(screen.getByText('Pending')).toBeInTheDocument();

      // Info message about checking inbox (Requirement 7.4)
      expect(screen.getByText(/verification email has been sent/i)).toBeInTheDocument();
    });

    it('renders verified status with green badge and success message', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('verified'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByText('tenant@example.com')).toBeInTheDocument();
      });

      expect(screen.getByText('Verified')).toBeInTheDocument();

      // Success message about emails being sent from their address
      expect(screen.getByText(/your email is verified/i)).toBeInTheDocument();
    });

    it('renders failed status with red badge and resend button', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('failed'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByText('tenant@example.com')).toBeInTheDocument();
      });

      expect(screen.getByText('Failed')).toBeInTheDocument();

      // Resend button should be visible (Requirement 7.3)
      expect(screen.getByRole('button', { name: /resend verification/i })).toBeInTheDocument();
    });

    it('renders expired status with orange badge and resend button', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('expired'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByText('tenant@example.com')).toBeInTheDocument();
      });

      expect(screen.getByText('Expired')).toBeInTheDocument();

      // Resend button should be visible (Requirement 7.3)
      expect(screen.getByRole('button', { name: /resend verification/i })).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Requirement 7.7: Fallback sender info when not verified
  // =========================================================================

  describe('Fallback sender display (Requirement 7.7)', () => {
    it('shows fallback sender info when status is pending', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('pending'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByText(/currently sent from the system address/i)).toBeInTheDocument();
      });
    });

    it('does not show fallback sender info when verified', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('verified'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });

      expect(screen.queryByText(/currently sent from the system address/i)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Requirement 7.3: Resend button with cooldown
  // =========================================================================

  describe('Resend button cooldown (Requirement 7.3)', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('disables resend button during cooldown and shows countdown', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('failed'));
      vi.mocked(resendVerification).mockResolvedValue({ success: true, message: 'Sent' });

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /resend verification/i })).toBeInTheDocument();
      });

      // Click resend
      const resendButton = screen.getByRole('button', { name: /resend verification/i });
      await act(async () => {
        fireEvent.click(resendButton);
      });

      // After successful resend, button should be disabled with countdown
      await waitFor(() => {
        const button = screen.getByRole('button', { name: /60s/i });
        expect(button).toBeDisabled();
      });

      // Advance timer by 1 second
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      // Should show 59s
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /59s/i })).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Requirement 7.5: Email update form validation
  // =========================================================================

  describe('Email update form validation (Requirement 7.5)', () => {
    it('shows validation error for invalid email', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('pending'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText('new-email@example.com')).toBeInTheDocument();
      });

      // Type invalid email and blur to trigger validation
      const emailInput = screen.getByPlaceholderText('new-email@example.com');
      fireEvent.change(emailInput, { target: { value: 'not-an-email' } });
      fireEvent.blur(emailInput);

      // Submit the form to trigger validation
      const submitButton = screen.getByRole('button', { name: /update email/i });
      fireEvent.click(submitButton);

      // Should show validation error
      await waitFor(() => {
        expect(screen.getByText(/please enter a valid email address/i)).toBeInTheDocument();
      });
    });

    it('submits valid email and shows success toast', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('pending'));
      vi.mocked(updateSenderEmail).mockResolvedValue({
        success: true,
        data: { email: 'new@example.com', status: 'pending' },
      });

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText('new-email@example.com')).toBeInTheDocument();
      });

      // Type valid email and submit
      const emailInput = screen.getByPlaceholderText('new-email@example.com');
      fireEvent.change(emailInput, { target: { value: 'new@example.com' } });

      const submitButton = screen.getByRole('button', { name: /update email/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(updateSenderEmail).toHaveBeenCalledWith('new@example.com');
      });

      // Should show success toast
      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Email updated',
            status: 'success',
          })
        );
      });
    });
  });

  // =========================================================================
  // API error handling and toast display
  // =========================================================================

  describe('API error handling and toast display', () => {
    it('shows error toast when getVerificationStatus fails', async () => {
      vi.mocked(getVerificationStatus).mockRejectedValue(new Error('Network error'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Failed to load verification status',
            status: 'error',
          })
        );
      });
    });

    it('shows error toast when resend verification fails', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('failed'));
      vi.mocked(resendVerification).mockRejectedValue(new Error('SES unavailable'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /resend verification/i })).toBeInTheDocument();
      });

      const resendButton = screen.getByRole('button', { name: /resend verification/i });
      fireEvent.click(resendButton);

      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Resend failed',
            status: 'error',
          })
        );
      });
    });

    it('shows error toast when email update fails', async () => {
      vi.mocked(getVerificationStatus).mockResolvedValue(createMockStatus('pending'));
      vi.mocked(updateSenderEmail).mockRejectedValue(new Error('Server error'));

      render(<SenderSettingsTab tenant="test-tenant" />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText('new-email@example.com')).toBeInTheDocument();
      });

      const emailInput = screen.getByPlaceholderText('new-email@example.com');
      fireEvent.change(emailInput, { target: { value: 'valid@example.com' } });

      const submitButton = screen.getByRole('button', { name: /update email/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Update failed',
            status: 'error',
          })
        );
      });
    });
  });

  // =========================================================================
  // Loading state
  // =========================================================================

  describe('Loading state', () => {
    it('shows loading spinner while fetching status', () => {
      vi.mocked(getVerificationStatus).mockReturnValue(new Promise(() => {})); // never resolves

      render(<SenderSettingsTab tenant="test-tenant" />);

      expect(screen.getByText(/loading sender settings/i)).toBeInTheDocument();
    });
  });
});
