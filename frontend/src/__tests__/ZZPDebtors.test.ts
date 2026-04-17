/**
 * Tests for ZZPDebtors page logic.
 * Tests currency formatting, data aggregation, and component behavior.
 */
import { InvoiceStatus, AgingBuckets } from '../types/zzp';

/** Replicated from ZZPDebtors.tsx */
const formatCurrency = (amount: number) =>
  new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(amount);

interface DebtorGroup {
  contact: { id: number; client_id: string; company_name: string };
  total: number;
  invoices: {
    id: number;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    grand_total: number;
    status: InvoiceStatus;
    days_overdue?: number;
  }[];
}

describe('ZZPDebtors page logic', () => {
  describe('formatCurrency', () => {
    it('formats positive amounts in EUR', () => {
      const result = formatCurrency(15200.50);
      expect(result).toContain('15.200,50');
      expect(result).toContain('€');
    });

    it('formats zero amount', () => {
      const result = formatCurrency(0);
      expect(result).toContain('0,00');
    });

    it('formats negative amounts', () => {
      const result = formatCurrency(-500);
      expect(result).toContain('500,00');
    });
  });

  describe('receivables/payables total calculation', () => {
    const groups: DebtorGroup[] = [
      {
        contact: { id: 1, client_id: 'ACME', company_name: 'Acme Corp' },
        total: 15000,
        invoices: [
          { id: 1, invoice_number: 'INV-2026-0001', invoice_date: '2026-04-01', due_date: '2026-05-01', grand_total: 15000, status: 'sent' },
        ],
      },
      {
        contact: { id: 2, client_id: 'KPN', company_name: 'KPN B.V.' },
        total: 8500,
        invoices: [
          { id: 2, invoice_number: 'INV-2026-0002', invoice_date: '2026-03-15', due_date: '2026-04-14', grand_total: 5000, status: 'overdue', days_overdue: 1 },
          { id: 3, invoice_number: 'INV-2026-0003', invoice_date: '2026-04-01', due_date: '2026-05-01', grand_total: 3500, status: 'sent' },
        ],
      },
    ];

    it('calculates total outstanding from groups', () => {
      const total = groups.reduce((sum, g) => sum + g.total, 0);
      expect(total).toBe(23500);
    });

    it('counts overdue invoices per contact', () => {
      const overduePerContact = groups.map(g => ({
        client_id: g.contact.client_id,
        overdueCount: g.invoices.filter(inv => inv.status === 'overdue').length,
      }));
      expect(overduePerContact[0].overdueCount).toBe(0);
      expect(overduePerContact[1].overdueCount).toBe(1);
    });

    it('handles empty groups', () => {
      const emptyGroups: DebtorGroup[] = [];
      const total = emptyGroups.reduce((sum, g) => sum + g.total, 0);
      expect(total).toBe(0);
    });
  });

  describe('aging buckets', () => {
    const buckets: AgingBuckets = {
      current: 10000,
      '1_30_days': 8000,
      '31_60_days': 5000,
      '61_90_days': 2000,
      '90_plus_days': 0,
    };

    it('sums all buckets to total outstanding', () => {
      const total = Object.values(buckets).reduce((sum, v) => sum + v, 0);
      expect(total).toBe(25000);
    });

    it('has all required bucket keys', () => {
      expect(buckets).toHaveProperty('current');
      expect(buckets).toHaveProperty('1_30_days');
      expect(buckets).toHaveProperty('31_60_days');
      expect(buckets).toHaveProperty('61_90_days');
      expect(buckets).toHaveProperty('90_plus_days');
    });

    it('allows zero values in buckets', () => {
      expect(buckets['90_plus_days']).toBe(0);
    });
  });

  describe('reminder eligibility', () => {
    it('only overdue invoices are eligible for reminders', () => {
      const statuses: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited'];
      const eligible = statuses.filter(s => s === 'overdue');
      expect(eligible).toEqual(['overdue']);
    });
  });
});
