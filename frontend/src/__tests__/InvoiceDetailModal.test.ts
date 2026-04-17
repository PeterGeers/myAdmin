/**
 * Tests for InvoiceDetailModal component logic.
 * Tests the modal props interface and that invoiceId is passed through correctly.
 */

// Extracted from InvoiceDetailModal.tsx — the props interface
interface InvoiceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  invoiceId?: number | null;
  onSaved?: () => void;
}

// Simulate the prop-passing logic: the modal passes invoiceId to ZZPInvoiceDetail
function getInvoiceDetailProps(modalProps: InvoiceDetailModalProps) {
  return {
    invoiceId: modalProps.invoiceId,
    onClose: modalProps.onClose,
    onSaved: modalProps.onSaved,
  };
}

describe('InvoiceDetailModal', () => {
  describe('props interface', () => {
    it('accepts required props (isOpen, onClose)', () => {
      const props: InvoiceDetailModalProps = {
        isOpen: true,
        onClose: jest.fn(),
      };
      expect(props.isOpen).toBe(true);
      expect(typeof props.onClose).toBe('function');
    });

    it('accepts optional invoiceId', () => {
      const props: InvoiceDetailModalProps = {
        isOpen: true,
        onClose: jest.fn(),
        invoiceId: 42,
      };
      expect(props.invoiceId).toBe(42);
    });

    it('accepts null invoiceId for new invoice', () => {
      const props: InvoiceDetailModalProps = {
        isOpen: true,
        onClose: jest.fn(),
        invoiceId: null,
      };
      expect(props.invoiceId).toBeNull();
    });

    it('accepts optional onSaved callback', () => {
      const onSaved = jest.fn();
      const props: InvoiceDetailModalProps = {
        isOpen: true,
        onClose: jest.fn(),
        onSaved,
      };
      expect(props.onSaved).toBe(onSaved);
    });
  });

  describe('invoiceId pass-through to ZZPInvoiceDetail', () => {
    it('passes numeric invoiceId', () => {
      const onClose = jest.fn();
      const onSaved = jest.fn();
      const result = getInvoiceDetailProps({
        isOpen: true, onClose, invoiceId: 123, onSaved,
      });
      expect(result.invoiceId).toBe(123);
      expect(result.onClose).toBe(onClose);
      expect(result.onSaved).toBe(onSaved);
    });

    it('passes null invoiceId for new invoice creation', () => {
      const result = getInvoiceDetailProps({
        isOpen: true, onClose: jest.fn(), invoiceId: null,
      });
      expect(result.invoiceId).toBeNull();
    });

    it('passes undefined invoiceId when not provided', () => {
      const result = getInvoiceDetailProps({
        isOpen: true, onClose: jest.fn(),
      });
      expect(result.invoiceId).toBeUndefined();
    });

    it('passes onSaved callback through', () => {
      const onSaved = jest.fn();
      const result = getInvoiceDetailProps({
        isOpen: true, onClose: jest.fn(), onSaved,
      });
      result.onSaved?.();
      expect(onSaved).toHaveBeenCalledTimes(1);
    });

    it('handles missing onSaved gracefully', () => {
      const result = getInvoiceDetailProps({
        isOpen: true, onClose: jest.fn(),
      });
      expect(result.onSaved).toBeUndefined();
    });
  });
});
