/**
 * Tests for ZZPTimeTracking page logic.
 * Tests monetary value calculation, billable filtering, summary grouping,
 * and unbilled entry selection for invoice creation.
 */
import { TimeEntry, TimeSummary } from '../types/zzp';

// Extracted from ZZPTimeTracking.tsx — monetary value calculation
function calculateMonetaryValue(hours: number, hourlyRate: number): number {
  return hours * hourlyRate;
}

// Extracted from ZZPTimeTracking.tsx — format currency
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(amount);
}

// Extracted from ZZPTimeTracking.tsx — billable/billed filtering logic
function filterByBillable(entries: TimeEntry[], isBillable?: boolean): TimeEntry[] {
  if (isBillable === undefined) return entries;
  return entries.filter(e => e.is_billable === isBillable);
}

function filterByBilled(entries: TimeEntry[], isBilled?: boolean): TimeEntry[] {
  if (isBilled === undefined) return entries;
  return entries.filter(e => e.is_billed === isBilled);
}

// Extracted from ZZPTimeTracking.tsx — summary chart data transformation
function transformSummaryData(summaryData: TimeSummary[]): { name: string; hours: number; amount: number }[] {
  return summaryData.map(s => ({
    name: s.project_name || s.period || `Contact ${s.contact_id}` || '—',
    hours: s.total_hours,
    amount: s.total_amount,
  }));
}

// Extracted from ZZPTimeTracking.tsx — unbilled entry selection logic
function getUnbilledSelected(entries: TimeEntry[], selectedIds: Set<number>): TimeEntry[] {
  return entries.filter(e => selectedIds.has(e.id) && !e.is_billed);
}

// Extracted from ZZPTimeTracking.tsx — validate all selected entries belong to same contact
function validateSameContact(entries: TimeEntry[], selectedIds: Set<number>): { valid: boolean; contactId?: number } {
  const selectedEntries = entries.filter(e => selectedIds.has(e.id));
  if (selectedEntries.length === 0) return { valid: false };
  const contactIds = new Set(selectedEntries.map(e => e.contact_id));
  if (contactIds.size > 1) return { valid: false };
  return { valid: true, contactId: selectedEntries[0].contact_id };
}

// Helper to create test entries
function makeEntry(overrides: Partial<TimeEntry> & { id: number }): TimeEntry {
  return {
    contact_id: 1,
    entry_date: '2026-04-15',
    hours: 8,
    hourly_rate: 95,
    is_billable: true,
    is_billed: false,
    ...overrides,
  };
}

describe('ZZPTimeTracking page logic', () => {
  describe('monetary value calculation', () => {
    it('calculates hours × hourly_rate', () => {
      expect(calculateMonetaryValue(8, 95)).toBe(760);
    });

    it('handles fractional hours', () => {
      expect(calculateMonetaryValue(2.5, 120)).toBe(300);
    });

    it('handles zero hours', () => {
      expect(calculateMonetaryValue(0, 95)).toBe(0);
    });

    it('handles zero rate', () => {
      expect(calculateMonetaryValue(8, 0)).toBe(0);
    });

    it('handles large values', () => {
      expect(calculateMonetaryValue(160, 150)).toBe(24000);
    });
  });

  describe('currency formatting', () => {
    it('formats EUR amounts in nl-NL locale', () => {
      const result = formatCurrency(760);
      expect(result).toContain('760');
      expect(result).toContain('€');
    });

    it('formats zero amount', () => {
      const result = formatCurrency(0);
      expect(result).toContain('0');
    });
  });

  describe('billable filtering', () => {
    const entries: TimeEntry[] = [
      makeEntry({ id: 1, is_billable: true }),
      makeEntry({ id: 2, is_billable: false }),
      makeEntry({ id: 3, is_billable: true }),
    ];

    it('returns all entries when filter is undefined', () => {
      expect(filterByBillable(entries, undefined)).toHaveLength(3);
    });

    it('filters billable entries', () => {
      const result = filterByBillable(entries, true);
      expect(result).toHaveLength(2);
      expect(result.every(e => e.is_billable)).toBe(true);
    });

    it('filters non-billable entries', () => {
      const result = filterByBillable(entries, false);
      expect(result).toHaveLength(1);
      expect(result[0].is_billable).toBe(false);
    });
  });

  describe('billed filtering', () => {
    const entries: TimeEntry[] = [
      makeEntry({ id: 1, is_billed: false }),
      makeEntry({ id: 2, is_billed: true }),
      makeEntry({ id: 3, is_billed: false }),
    ];

    it('returns all entries when filter is undefined', () => {
      expect(filterByBilled(entries, undefined)).toHaveLength(3);
    });

    it('filters billed entries', () => {
      const result = filterByBilled(entries, true);
      expect(result).toHaveLength(1);
      expect(result[0].is_billed).toBe(true);
    });

    it('filters unbilled entries', () => {
      const result = filterByBilled(entries, false);
      expect(result).toHaveLength(2);
      expect(result.every(e => !e.is_billed)).toBe(true);
    });
  });

  describe('summary grouping transformation', () => {
    it('transforms contact-grouped summary', () => {
      const data: TimeSummary[] = [
        { contact_id: 1, total_hours: 40, total_amount: 3800 },
        { contact_id: 2, total_hours: 20, total_amount: 2400 },
      ];
      const result = transformSummaryData(data);
      expect(result).toHaveLength(2);
      expect(result[0].name).toBe('Contact 1');
      expect(result[0].hours).toBe(40);
      expect(result[0].amount).toBe(3800);
    });

    it('transforms project-grouped summary', () => {
      const data: TimeSummary[] = [
        { project_name: 'Website Redesign', total_hours: 80, total_amount: 7600 },
        { project_name: 'API Development', total_hours: 40, total_amount: 3800 },
      ];
      const result = transformSummaryData(data);
      expect(result[0].name).toBe('Website Redesign');
      expect(result[1].name).toBe('API Development');
    });

    it('transforms period-grouped summary', () => {
      const data: TimeSummary[] = [
        { period: '2026-01', total_hours: 160, total_amount: 15200 },
        { period: '2026-02', total_hours: 140, total_amount: 13300 },
      ];
      const result = transformSummaryData(data);
      expect(result[0].name).toBe('2026-01');
      expect(result[1].name).toBe('2026-02');
    });

    it('handles empty summary', () => {
      expect(transformSummaryData([])).toHaveLength(0);
    });
  });

  describe('unbilled entry selection', () => {
    const entries: TimeEntry[] = [
      makeEntry({ id: 1, is_billed: false }),
      makeEntry({ id: 2, is_billed: true }),
      makeEntry({ id: 3, is_billed: false }),
      makeEntry({ id: 4, is_billed: false }),
    ];

    it('returns only unbilled selected entries', () => {
      const selected = new Set([1, 2, 3]);
      const result = getUnbilledSelected(entries, selected);
      expect(result).toHaveLength(2);
      expect(result.map(e => e.id)).toEqual([1, 3]);
    });

    it('returns empty when no entries selected', () => {
      const result = getUnbilledSelected(entries, new Set());
      expect(result).toHaveLength(0);
    });

    it('excludes billed entries from selection', () => {
      const selected = new Set([2]); // entry 2 is billed
      const result = getUnbilledSelected(entries, selected);
      expect(result).toHaveLength(0);
    });
  });

  describe('same-contact validation for invoice creation', () => {
    const entries: TimeEntry[] = [
      makeEntry({ id: 1, contact_id: 10 }),
      makeEntry({ id: 2, contact_id: 10 }),
      makeEntry({ id: 3, contact_id: 20 }),
    ];

    it('validates when all selected entries belong to same contact', () => {
      const result = validateSameContact(entries, new Set([1, 2]));
      expect(result.valid).toBe(true);
      expect(result.contactId).toBe(10);
    });

    it('rejects when selected entries belong to different contacts', () => {
      const result = validateSameContact(entries, new Set([1, 3]));
      expect(result.valid).toBe(false);
    });

    it('rejects when no entries selected', () => {
      const result = validateSameContact(entries, new Set());
      expect(result.valid).toBe(false);
    });

    it('validates single entry selection', () => {
      const result = validateSameContact(entries, new Set([3]));
      expect(result.valid).toBe(true);
      expect(result.contactId).toBe(20);
    });
  });
});
