/**
 * Unit Tests for EmailPreviewPanel Component
 *
 * Tests rendering of email fields, BCC display, and confirm send callback.
 * Reference: .kiro/specs/zzp-invoice-pdf-preview/tasks.md Task 9.2
 *
 * Requirements: 8.8, 8.11, 8.12
 */

import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent } from '@/test-utils';
import { EmailPreviewPanel } from '../components/zzp/EmailPreviewPanel';

// Mock useTypedTranslation to return the key as-is (with optional fallback)
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

const mockEmailPreview = {
  subject: 'Factuur INV-2024-001 van Company BV',
  html_body: '<p>Geachte Client BV,</p><p>Bijgevoegd vindt u factuur INV-2024-001.</p>',
  recipient: 'client@example.com',
  bcc: 'admin@freelancer.nl',
  attachment_filename: 'INV-2024-001.pdf',
};

describe('EmailPreviewPanel', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirmSend: vi.fn(),
    emailPreview: mockEmailPreview,
    isSending: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering email fields', () => {
    it('renders the subject field', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText(mockEmailPreview.subject)).toBeInTheDocument();
    });

    it('renders the recipient email', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText(mockEmailPreview.recipient)).toBeInTheDocument();
    });

    it('renders the BCC field with tenant admin email', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText(mockEmailPreview.bcc)).toBeInTheDocument();
    });

    it('renders the attachment filename', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText(`📎 ${mockEmailPreview.attachment_filename}`)).toBeInTheDocument();
    });

    it('renders the HTML body content', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText('Geachte Client BV,')).toBeInTheDocument();
    });

    it('renders field labels using translation keys', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText('invoices.email.recipientLabel')).toBeInTheDocument();
      expect(screen.getByText('invoices.email.bccLabel')).toBeInTheDocument();
      expect(screen.getByText('invoices.email.subjectLabel')).toBeInTheDocument();
      expect(screen.getByText('invoices.email.attachmentLabel')).toBeInTheDocument();
    });
  });

  describe('BCC field displays tenant admin email', () => {
    it('shows the admin email in the BCC section', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      // BCC label should be present
      expect(screen.getByText('invoices.email.bccLabel')).toBeInTheDocument();
      // Admin email should be displayed
      expect(screen.getByText('admin@freelancer.nl')).toBeInTheDocument();
    });

    it('shows a different admin email when provided', () => {
      const customPreview = {
        ...mockEmailPreview,
        bcc: 'other-admin@company.nl',
      };
      render(<EmailPreviewPanel {...defaultProps} emailPreview={customPreview} />);
      expect(screen.getByText('other-admin@company.nl')).toBeInTheDocument();
    });
  });

  describe('Confirm send button', () => {
    it('triggers onConfirmSend callback when clicked', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      const sendButton = screen.getByText('invoices.email.sendButton');
      fireEvent.click(sendButton);
      expect(defaultProps.onConfirmSend).toHaveBeenCalledTimes(1);
    });

    it('is disabled when isSending is true', () => {
      render(<EmailPreviewPanel {...defaultProps} isSending={true} />);
      const sendButton = screen.getByText('invoices.email.sendButton');
      expect(sendButton).toBeDisabled();
    });

    it('is disabled when emailPreview is null', () => {
      render(<EmailPreviewPanel {...defaultProps} emailPreview={null} />);
      const sendButton = screen.getByText('invoices.email.sendButton');
      expect(sendButton).toBeDisabled();
    });
  });

  describe('Loading state', () => {
    it('shows spinner when emailPreview is null', () => {
      render(<EmailPreviewPanel {...defaultProps} emailPreview={null} />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('does not show spinner when emailPreview is provided', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
  });

  describe('Modal behavior', () => {
    it('does not render when isOpen is false', () => {
      render(<EmailPreviewPanel {...defaultProps} isOpen={false} />);
      expect(screen.queryByText(mockEmailPreview.subject)).not.toBeInTheDocument();
    });

    it('renders panel title', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      expect(screen.getByText('invoices.email.panelTitle')).toBeInTheDocument();
    });

    it('renders cancel button that calls onClose', () => {
      render(<EmailPreviewPanel {...defaultProps} />);
      const cancelButton = screen.getByText('Cancel');
      fireEvent.click(cancelButton);
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });
  });
});
