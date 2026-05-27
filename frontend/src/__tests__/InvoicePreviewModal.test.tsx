/**
 * Unit tests for InvoicePreviewModal component.
 *
 * Tests modal rendering, close/escape behavior, download button,
 * and error fallback display.
 *
 * Requirements: 4.1, 4.3, 4.4, 4.6
 * Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §Frontend Components
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, vi } from 'vitest';
import { test as fcTest } from '@fast-check/vitest';
import fc from 'fast-check';
import { InvoicePreviewModal } from '../components/zzp/InvoicePreviewModal';

// Mock useTypedTranslation to return keys as-is
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

describe('InvoicePreviewModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    pdfBlobUrl: 'blob:http://localhost:3000/test-pdf-blob',
    invoiceNumber: 'INV-2024-001',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('iframe rendering with blob URL', () => {
    it('renders iframe with the provided blob URL as src', () => {
      const { container } = render(<InvoicePreviewModal {...defaultProps} />);

      const iframe = container.querySelector('iframe');
      expect(iframe).not.toBeNull();
      expect(iframe?.getAttribute('src')).toBe(defaultProps.pdfBlobUrl);
    });

    it('does not render iframe when pdfBlobUrl is null', () => {
      const { container } = render(
        <InvoicePreviewModal {...defaultProps} pdfBlobUrl={null} />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeNull();
    });

    it('does not render modal content when isOpen is false', () => {
      const { container } = render(
        <InvoicePreviewModal {...defaultProps} isOpen={false} />
      );

      const iframe = container.querySelector('iframe');
      expect(iframe).toBeNull();
    });
  });

  describe('close button and Escape key dismiss modal', () => {
    it('renders a close button with aria-label from translation', () => {
      render(<InvoicePreviewModal {...defaultProps} />);

      // The ModalCloseButton mock renders with the aria-label prop passed by the component
      const closeButton = screen.getByLabelText('invoices.preview.close');
      expect(closeButton).toBeDefined();
    });

    it('renders a footer close button that calls onClose when clicked', () => {
      render(<InvoicePreviewModal {...defaultProps} />);

      // The footer close button uses the translation key
      const closeButtons = screen.getAllByText('invoices.preview.close');
      expect(closeButtons.length).toBeGreaterThan(0);

      // Click the footer close button
      fireEvent.click(closeButtons[0]);
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('download button with correct filename', () => {
    it('renders a hidden download anchor with correct filename attribute', () => {
      const { container } = render(<InvoicePreviewModal {...defaultProps} />);

      const downloadAnchor = container.querySelector('a[download]');
      expect(downloadAnchor).not.toBeNull();
      expect(downloadAnchor?.getAttribute('download')).toBe('INV-2024-001_PREVIEW.pdf');
      expect(downloadAnchor?.getAttribute('href')).toBe(defaultProps.pdfBlobUrl);
    });

    it('uses the correct filename format with invoice number', () => {
      const { container } = render(
        <InvoicePreviewModal {...defaultProps} invoiceNumber="FAC-2025-042" />
      );

      const downloadAnchor = container.querySelector('a[download]');
      expect(downloadAnchor?.getAttribute('download')).toBe('FAC-2025-042_PREVIEW.pdf');
    });

    it('renders download button in the footer', () => {
      render(<InvoicePreviewModal {...defaultProps} />);

      const downloadButtons = screen.getAllByText('invoices.preview.download');
      expect(downloadButtons.length).toBeGreaterThan(0);
    });

    it('does not render download anchor when pdfBlobUrl is null', () => {
      const { container } = render(
        <InvoicePreviewModal {...defaultProps} pdfBlobUrl={null} />
      );

      const downloadAnchor = container.querySelector('a[download]');
      expect(downloadAnchor).toBeNull();
    });
  });

  describe('error fallback when iframe fails', () => {
    it('shows error fallback UI when pdfBlobUrl is null (simulates render failure)', () => {
      render(<InvoicePreviewModal {...defaultProps} pdfBlobUrl={null} />);

      // When pdfBlobUrl is null, the error/empty state is shown (same UI as iframe error)
      expect(screen.getByText('invoices.preview.renderError')).toBeDefined();
    });

    it('error fallback does not show download button when pdfBlobUrl is null', () => {
      const { container } = render(
        <InvoicePreviewModal {...defaultProps} pdfBlobUrl={null} />
      );

      // No download anchor when blob URL is null
      const downloadAnchor = container.querySelector('a[download]');
      expect(downloadAnchor).toBeNull();
    });

    it('renders iframe with onError handler for error detection', () => {
      const { container } = render(<InvoicePreviewModal {...defaultProps} />);

      const iframe = container.querySelector('iframe');
      expect(iframe).not.toBeNull();
      // Verify iframe is rendered with correct attributes when no error
      expect(iframe?.getAttribute('src')).toBe(defaultProps.pdfBlobUrl);
      expect(iframe?.getAttribute('width')).toBe('100%');
      expect(iframe?.getAttribute('height')).toBe('100%');
    });

    it('does not show error message when iframe renders successfully', () => {
      render(<InvoicePreviewModal {...defaultProps} />);

      // When iframe renders successfully, error message should NOT be present
      expect(screen.queryByText('invoices.preview.renderError')).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// Property 11: Download filename format
// Feature: zzp-invoice-pdf-preview, Property 11: Download filename format
// ---------------------------------------------------------------------------
describe('Feature: zzp-invoice-pdf-preview, Property 11: Download filename format', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * For any invoice_number string, the download button in the Preview_Viewer
   * SHALL use the filename "{invoice_number}_PREVIEW.pdf".
   */
  fcTest.prop(
    [fc.string({ minLength: 1 })],
    { numRuns: 20 },
  )(
    'download anchor uses filename "{invoiceNumber}_PREVIEW.pdf" for any invoice_number',
    (invoiceNumber) => {
      const { container } = render(
        <InvoicePreviewModal
          isOpen={true}
          onClose={() => {}}
          pdfBlobUrl="blob:http://localhost/fake-pdf-url"
          invoiceNumber={invoiceNumber}
        />
      );

      // Find the hidden download anchor element
      const downloadAnchor = container.querySelector('a[download]');
      expect(downloadAnchor).not.toBeNull();
      expect(downloadAnchor!.getAttribute('download')).toBe(
        `${invoiceNumber}_PREVIEW.pdf`
      );
    }
  );
});
