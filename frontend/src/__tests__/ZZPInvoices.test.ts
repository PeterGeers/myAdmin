/**
 * Tests for ZZPInvoices page logic.
 * Tests CSV export generation and currency formatting.
 */
import { Invoice, InvoiceStatus } from '../types/zzp';

// Extracted from ZZPInvoices.tsx
const STATUSES: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited'];

function formatCurrency(amount: number, currency = 'EUR') {
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency }).format(amount);
}

function generateCsv(invoices: Partial<Invoice>[]) {
  const csvRows = [
    ['Invoice Number', 'Contact', 'Date', 'Due Date', 'Status', 'Total'].join(','),
    ...invoices.map(inv =>
      [inv.invoice_number, inv.contact?.company_name || '', inv.invoice_date,
       inv.due_date, inv.status, (inv.grand_total || 0).toFixed(2)].join(',')
    ),
  ];
  return csvRows.join('\n');
}

describe('ZZPInvoices page logic', () => {
  describe('STATUSES constant', () => {
    it('contains all 6 invoice statuses', () => {
      expect(STATUSES).toHaveLength(6);
      expect(STATUSES).toContain('draft');
      expect(STATUSES).toContain('sent');
      expect(STATUSES).toContain('paid');
      expect(STATUSES).toContain('overdue');
      expect(STATUSES).toContain('cancelled');
      expect(STATUSES).toContain('credited');
    });
  });

  describe('formatCurrency', () => {
    it('formats EUR amounts in nl-NL locale', () => {
      const result = formatCurrency(15200);
      expect(result).toContain('15.200');
      expect(result).toContain('€');
    });

    it('formats zero amount', () => {
      const result = formatCurrency(0);
      expect(result).toContain('0');
    });

    it('formats with different currency', () => {
      const result = formatCurrency(1000, 'USD');
      expect(result).toContain('1.000');
      expect(result).toContain('US$');
    });
  });

  describe('CSV export', () => {
    it('generates header row', () => {
      const csv = generateCsv([]);
      expect(csv).toBe('Invoice Number,Contact,Date,Due Date,Status,Total');
    });

    it('generates data rows', () => {
      const invoices: Partial<Invoice>[] = [
        {
          invoice_number: 'INV-2026-0001',
          contact: { id: 1, client_id: 'ACME', company_name: 'Acme Corp' },
          invoice_date: '2026-04-15',
          due_date: '2026-05-15',
          status: 'draft',
          grand_total: 18392.00,
        },
      ];
      const csv = generateCsv(invoices);
      const lines = csv.split('\n');
      expect(lines).toHaveLength(2);
      expect(lines[1]).toContain('INV-2026-0001');
      expect(lines[1]).toContain('Acme Corp');
      expect(lines[1]).toContain('18392.00');
    });

    it('handles missing contact gracefully', () => {
      const invoices: Partial<Invoice>[] = [
        { invoice_number: 'INV-2026-0002', invoice_date: '2026-04-15',
          due_date: '2026-05-15', status: 'draft', grand_total: 100 },
      ];
      const csv = generateCsv(invoices);
      expect(csv).toContain('INV-2026-0002,,2026-04-15');
    });

    it('handles multiple invoices', () => {
      const invoices: Partial<Invoice>[] = [
        { invoice_number: 'INV-001', contact: { id: 1, client_id: 'A', company_name: 'A Corp' },
          invoice_date: '2026-01-01', due_date: '2026-02-01', status: 'paid', grand_total: 500 },
        { invoice_number: 'INV-002', contact: { id: 2, client_id: 'B', company_name: 'B Corp' },
          invoice_date: '2026-02-01', due_date: '2026-03-01', status: 'sent', grand_total: 1000 },
      ];
      const csv = generateCsv(invoices);
      const lines = csv.split('\n');
      expect(lines).toHaveLength(3);
    });
  });
});
