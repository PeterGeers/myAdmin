/**
 * Tests for ZZPInvoiceDetail page logic.
 * Tests computed totals, editability rules, and payload construction.
 */
import { InvoiceLine, InvoiceInput } from '../types/zzp';

// Extracted logic from ZZPInvoiceDetail.tsx

function computeSubtotal(lines: Partial<InvoiceLine>[]): number {
  return lines.reduce((sum, l) => sum + (l.line_total || 0), 0);
}

function isEditable(invoiceStatus: string | null): boolean {
  return !invoiceStatus || invoiceStatus === 'draft';
}

function buildPayload(
  contactId: number, invoiceDate: string, paymentTermsDays: number,
  currency: string, exchangeRate: number, notes: string,
  lines: Partial<InvoiceLine>[],
): InvoiceInput {
  return {
    contact_id: contactId,
    invoice_date: invoiceDate,
    payment_terms_days: paymentTermsDays,
    currency,
    exchange_rate: exchangeRate,
    notes: notes || undefined,
    lines: lines.map((l, idx) => ({
      product_id: l.product_id || undefined,
      description: l.description || '',
      quantity: Number(l.quantity) || 0,
      unit_price: Number(l.unit_price) || 0,
      vat_code: l.vat_code || 'high',
      sort_order: idx,
    })),
  };
}

describe('ZZPInvoiceDetail logic', () => {
  describe('computeSubtotal', () => {
    it('sums line totals', () => {
      const lines: Partial<InvoiceLine>[] = [
        { line_total: 1000 }, { line_total: 500 }, { line_total: 250 },
      ];
      expect(computeSubtotal(lines)).toBe(1750);
    });

    it('returns 0 for empty lines', () => {
      expect(computeSubtotal([])).toBe(0);
    });

    it('handles undefined line_total', () => {
      const lines: Partial<InvoiceLine>[] = [
        { line_total: 100 }, { description: 'no total' },
      ];
      expect(computeSubtotal(lines)).toBe(100);
    });
  });

  describe('isEditable', () => {
    it('returns true for null status (new invoice)', () => {
      expect(isEditable(null)).toBe(true);
    });

    it('returns true for draft status', () => {
      expect(isEditable('draft')).toBe(true);
    });

    it('returns false for sent status', () => {
      expect(isEditable('sent')).toBe(false);
    });

    it('returns false for paid status', () => {
      expect(isEditable('paid')).toBe(false);
    });

    it('returns false for overdue status', () => {
      expect(isEditable('overdue')).toBe(false);
    });

    it('returns false for credited status', () => {
      expect(isEditable('credited')).toBe(false);
    });
  });

  describe('buildPayload', () => {
    it('constructs valid InvoiceInput', () => {
      const lines: Partial<InvoiceLine>[] = [
        { product_id: 1, description: 'Dev work', quantity: 160, unit_price: 95, vat_code: 'high' },
      ];
      const payload = buildPayload(1, '2026-04-15', 30, 'EUR', 1, 'Test notes', lines);

      expect(payload.contact_id).toBe(1);
      expect(payload.invoice_date).toBe('2026-04-15');
      expect(payload.payment_terms_days).toBe(30);
      expect(payload.currency).toBe('EUR');
      expect(payload.notes).toBe('Test notes');
      expect(payload.lines).toHaveLength(1);
      expect(payload.lines[0].description).toBe('Dev work');
      expect(payload.lines[0].quantity).toBe(160);
      expect(payload.lines[0].sort_order).toBe(0);
    });

    it('omits empty notes', () => {
      const payload = buildPayload(1, '2026-04-15', 30, 'EUR', 1, '', []);
      expect(payload.notes).toBeUndefined();
    });

    it('defaults vat_code to high', () => {
      const lines: Partial<InvoiceLine>[] = [{ description: 'Test', quantity: 1, unit_price: 100 }];
      const payload = buildPayload(1, '2026-04-15', 30, 'EUR', 1, '', lines);
      expect(payload.lines[0].vat_code).toBe('high');
    });

    it('assigns sort_order by index', () => {
      const lines: Partial<InvoiceLine>[] = [
        { description: 'A', quantity: 1, unit_price: 10, vat_code: 'high' },
        { description: 'B', quantity: 2, unit_price: 20, vat_code: 'low' },
        { description: 'C', quantity: 3, unit_price: 30, vat_code: 'zero' },
      ];
      const payload = buildPayload(1, '2026-04-15', 30, 'EUR', 1, '', lines);
      expect(payload.lines[0].sort_order).toBe(0);
      expect(payload.lines[1].sort_order).toBe(1);
      expect(payload.lines[2].sort_order).toBe(2);
    });

    it('handles missing product_id', () => {
      const lines: Partial<InvoiceLine>[] = [{ description: 'Custom', quantity: 1, unit_price: 50, vat_code: 'high' }];
      const payload = buildPayload(1, '2026-04-15', 30, 'EUR', 1, '', lines);
      expect(payload.lines[0].product_id).toBeUndefined();
    });
  });
});
