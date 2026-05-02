/**
 * Preservation Property Tests — Filter Framework Migration
 *
 * Property 2: Preservation — Filter Output Equivalence
 * Property 3: Preservation — Sort Output Equivalence
 *
 * These tests verify that `useFilterableTable` produces correct filter/sort
 * output for the data types used in each migrated component. The reference
 * implementation uses case-insensitive substring matching with AND logic
 * across all active filters.
 *
 * **Validates: Requirements 3.1, 3.2, 3.4, 3.6**
 */
import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useFilterableTable } from '../hooks/useFilterableTable';

// ---------------------------------------------------------------------------
// Data type interfaces (matching migrated components)
// ---------------------------------------------------------------------------

interface BnbRecord {
  checkinDate: string;
  checkoutDate: string;
  channel: string;
  listing: string;
  nights: number;
  amountGross: number;
  amountNett: number;
  guestName: string;
  guests: number;
  reservationCode: string;
}

interface EmailLogEntry {
  id: number;
  recipient: string;
  email_type: string;
  administration: string;
  status: string;
  ses_message_id: string;
  subject: string;
  sent_by: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface Booking {
  reservationCode: string;
  guestName: string;
  channel: string;
  listing: string;
  checkinDate: string;
  checkoutDate: string;
  nights: number;
  guests: number;
  amountGross: number;
}

// ---------------------------------------------------------------------------
// INITIAL_FILTERS constants (matching migrated components)
// ---------------------------------------------------------------------------

const BNB_INITIAL_FILTERS: Record<string, string> = {
  channel: '', listing: '', guestName: '', checkinDate: '', checkoutDate: '',
};

const EMAIL_INITIAL_FILTERS: Record<string, string> = {
  recipient: '', email_type: '', subject: '', sent_by: '', status: '',
};

const STR_INITIAL_FILTERS: Record<string, string> = {
  reservationCode: '', guestName: '', channel: '', listing: '',
  checkinDate: '', nights: '', amountGross: '',
};

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const dateStr = fc.constantFrom(
  '2024-01-15', '2024-03-20', '2024-06-01', '2024-09-10', '2024-12-25',
);

const channelStr = fc.constantFrom('Airbnb', 'Booking.com', 'Direct', 'VRBO', 'Expedia');
const listingStr = fc.constantFrom('Beach House', 'City Apt', 'Mountain Lodge', 'Lake View');
const nameStr = fc.constantFrom('John Smith', 'Jane Doe', 'Peter Pan', 'Alice Wonder', 'Bob Builder');
const statusStr = fc.constantFrom('delivered', 'bounced', 'pending', 'failed', 'sent');

const bnbRecordArb: fc.Arbitrary<BnbRecord> = fc.record({
  checkinDate: dateStr,
  checkoutDate: dateStr,
  channel: channelStr,
  listing: listingStr,
  nights: fc.integer({ min: 1, max: 30 }),
  amountGross: fc.double({ min: 50, max: 5000, noNaN: true }),
  amountNett: fc.double({ min: 40, max: 4500, noNaN: true }),
  guestName: nameStr,
  guests: fc.integer({ min: 1, max: 10 }),
  reservationCode: fc.stringMatching(/^[A-Z0-9]{6,10}$/),
});

const emailLogArb: fc.Arbitrary<EmailLogEntry> = fc.record({
  id: fc.integer({ min: 1, max: 10000 }),
  recipient: fc.stringMatching(/^[a-z]{3,8}@[a-z]{3,6}\.[a-z]{2,3}$/),
  email_type: fc.constantFrom('invoice', 'reminder', 'confirmation', 'notification'),
  administration: fc.constantFrom('Admin1', 'Admin2', 'Admin3'),
  status: statusStr,
  ses_message_id: fc.stringMatching(/^[a-f0-9]{8}$/),
  subject: fc.constantFrom('Invoice #123', 'Payment Reminder', 'Booking Confirmed', 'Welcome'),
  sent_by: fc.constantFrom('system', 'admin', 'user'),
  error_message: fc.constantFrom(null, 'timeout', 'invalid address'),
  created_at: dateStr,
  updated_at: dateStr,
});

const bookingArb: fc.Arbitrary<Booking> = fc.record({
  reservationCode: fc.stringMatching(/^[A-Z0-9]{6,10}$/),
  guestName: nameStr,
  channel: channelStr,
  listing: listingStr,
  checkinDate: dateStr,
  checkoutDate: dateStr,
  nights: fc.integer({ min: 1, max: 30 }),
  guests: fc.integer({ min: 1, max: 10 }),
  amountGross: fc.double({ min: 50, max: 5000, noNaN: true }),
});

// Short filter string that could match substrings in data
const filterStr = fc.stringMatching(/^[a-zA-Z0-9]{0,4}$/);

const directionArb = fc.constantFrom('asc' as const, 'desc' as const);

// ---------------------------------------------------------------------------
// Reference implementations
// ---------------------------------------------------------------------------

/**
 * Reference filter: case-insensitive substring matching with AND logic.
 * This matches the behavior of useColumnFilters' applyFilters function.
 */
function referenceFilter<T extends Record<string, any>>(
  data: T[],
  filters: Record<string, string>,
): T[] {
  const active = Object.entries(filters).filter(([, v]) => v !== '');
  if (active.length === 0) return data;
  return data.filter(row =>
    active.every(([key, filterValue]) => {
      if (!(key in row)) return true;
      return String(row[key] ?? '').toLowerCase().includes(filterValue.toLowerCase());
    }),
  );
}

/**
 * Reference sort: matches useTableSort's compareValues logic.
 * - null/undefined sort to end regardless of direction
 * - Both numbers → numeric comparison
 * - Both ISO date strings → chronological comparison
 * - Otherwise → case-insensitive string comparison
 */
function referenceSort<T extends Record<string, any>>(
  data: T[],
  field: string,
  direction: 'asc' | 'desc',
): T[] {
  const multiplier = direction === 'asc' ? 1 : -1;
  return [...data].sort((a, b) => {
    const aVal = a[field];
    const bVal = b[field];

    const aN = aVal === null || aVal === undefined;
    const bN = bVal === null || bVal === undefined;
    if (aN && bN) return 0;
    if (aN) return 1;
    if (bN) return -1;

    // Both numbers
    if (typeof aVal === 'number' && Number.isFinite(aVal) &&
        typeof bVal === 'number' && Number.isFinite(bVal)) {
      return (aVal - bVal) * multiplier;
    }

    // Both ISO date strings
    const dateRegex = /^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$/;
    if (typeof aVal === 'string' && typeof bVal === 'string' &&
        dateRegex.test(aVal) && dateRegex.test(bVal) &&
        Number.isFinite(Date.parse(aVal)) && Number.isFinite(Date.parse(bVal))) {
      return (Date.parse(aVal) - Date.parse(bVal)) * multiplier;
    }

    // Fallback: case-insensitive string comparison
    return String(aVal).localeCompare(String(bVal), undefined, { sensitivity: 'base' }) * multiplier;
  });
}

// ---------------------------------------------------------------------------
// Property 2: BnbRevenueReport Filter Equivalence
// ---------------------------------------------------------------------------

describe('Preservation — BnbRevenueReport Filter Equivalence', () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * For random BnbRecord[] + filter strings, verify useFilterableTable output
   * matches case-insensitive substring matching on channel, listing, guestName.
   */
  it('PROPERTY: filter output matches reference for channel, listing, guestName', () => {
    fc.assert(
      fc.property(
        fc.array(bnbRecordArb, { minLength: 0, maxLength: 20 }),
        fc.record({
          channel: filterStr,
          listing: filterStr,
          guestName: filterStr,
        }),
        (data, filterValues) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<BnbRecord>(data, {
                initialFilters: BNB_INITIAL_FILTERS,
                defaultSort: { field: 'checkinDate', direction: 'desc' },
              }),
            );

            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                if (value !== '') result.current.setFilter(key, value);
              }
            });
            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const fullFilters = { ...BNB_INITIAL_FILTERS, ...filterValues };
            const expectedFiltered = referenceFilter(data, fullFilters);

            // Same rows (ignoring sort order since we test sort separately)
            expect(hookOutput.length).toBe(expectedFiltered.length);
            for (const row of hookOutput) {
              expect(expectedFiltered).toContainEqual(row);
            }
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3: BnbRevenueReport Sort Equivalence
// ---------------------------------------------------------------------------

describe('Preservation — BnbRevenueReport Sort Equivalence', () => {
  /**
   * **Validates: Requirements 3.2**
   *
   * For random BnbRecord[] + sort field/direction, verify hook sort works
   * correctly for string, numeric, and date fields.
   */
  it('PROPERTY: sort output matches reference for string fields', () => {
    fc.assert(
      fc.property(
        fc.array(bnbRecordArb, { minLength: 0, maxLength: 20 }),
        fc.constantFrom('channel', 'listing', 'guestName'),
        directionArb,
        (data, sortField, sortDirection) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<BnbRecord>(data, {
                initialFilters: BNB_INITIAL_FILTERS,
                defaultSort: { field: sortField, direction: sortDirection },
              }),
            );

            // No filters applied — just testing sort
            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const expectedSorted = referenceSort(data, sortField, sortDirection);

            expect(hookOutput).toEqual(expectedSorted);
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('PROPERTY: sort output matches reference for numeric fields', () => {
    fc.assert(
      fc.property(
        fc.array(bnbRecordArb, { minLength: 0, maxLength: 20 }),
        fc.constantFrom('nights', 'amountGross', 'amountNett', 'guests'),
        directionArb,
        (data, sortField, sortDirection) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<BnbRecord>(data, {
                initialFilters: BNB_INITIAL_FILTERS,
                defaultSort: { field: sortField, direction: sortDirection },
              }),
            );

            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const expectedSorted = referenceSort(data, sortField, sortDirection);

            expect(hookOutput).toEqual(expectedSorted);
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('PROPERTY: sort output matches reference for date fields', () => {
    fc.assert(
      fc.property(
        fc.array(bnbRecordArb, { minLength: 0, maxLength: 20 }),
        fc.constantFrom('checkinDate', 'checkoutDate'),
        directionArb,
        (data, sortField, sortDirection) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<BnbRecord>(data, {
                initialFilters: BNB_INITIAL_FILTERS,
                defaultSort: { field: sortField, direction: sortDirection },
              }),
            );

            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const expectedSorted = referenceSort(data, sortField, sortDirection);

            expect(hookOutput).toEqual(expectedSorted);
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: EmailLogPanel Filter Equivalence
// ---------------------------------------------------------------------------

describe('Preservation — EmailLogPanel Filter Equivalence', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * For random EmailLogEntry[] + filter strings, verify hook output matches
   * case-insensitive substring filtering on recipient, email_type, subject,
   * sent_by, status.
   */
  it('PROPERTY: filter output matches reference for all email log filter fields', () => {
    fc.assert(
      fc.property(
        fc.array(emailLogArb, { minLength: 0, maxLength: 20 }),
        fc.record({
          recipient: filterStr,
          email_type: filterStr,
          subject: filterStr,
          sent_by: filterStr,
          status: filterStr,
        }),
        (data, filterValues) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<EmailLogEntry>(data, {
                initialFilters: EMAIL_INITIAL_FILTERS,
                defaultSort: { field: 'created_at', direction: 'desc' },
              }),
            );

            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                if (value !== '') result.current.setFilter(key, value);
              }
            });
            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const fullFilters = { ...EMAIL_INITIAL_FILTERS, ...filterValues };
            const expectedFiltered = referenceFilter(data, fullFilters);

            expect(hookOutput.length).toBe(expectedFiltered.length);
            for (const row of hookOutput) {
              expect(expectedFiltered).toContainEqual(row);
            }
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: STRInvoice Filter Migration
// ---------------------------------------------------------------------------

describe('Preservation — STRInvoice Filter Migration', () => {
  /**
   * **Validates: Requirements 3.6**
   *
   * For random Booking[] + per-column filter strings, verify hook per-column
   * filtering produces correct subset. Per-column filtering is stricter than
   * the original all-column search — this tests the new (correct) behavior.
   */
  it('PROPERTY: per-column filter output matches reference for booking fields', () => {
    fc.assert(
      fc.property(
        fc.array(bookingArb, { minLength: 0, maxLength: 20 }),
        fc.record({
          reservationCode: filterStr,
          guestName: filterStr,
          channel: filterStr,
          listing: filterStr,
          checkinDate: filterStr,
          nights: filterStr,
          amountGross: filterStr,
        }),
        (data, filterValues) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<Booking>(data, {
                initialFilters: STR_INITIAL_FILTERS,
                defaultSort: { field: 'checkinDate', direction: 'desc' },
              }),
            );

            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                if (value !== '') result.current.setFilter(key, value);
              }
            });
            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;
            const fullFilters = { ...STR_INITIAL_FILTERS, ...filterValues };
            const expectedFiltered = referenceFilter(data, fullFilters);

            expect(hookOutput.length).toBe(expectedFiltered.length);
            for (const row of hookOutput) {
              expect(expectedFiltered).toContainEqual(row);
            }
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 3.6**
   *
   * Verify that filtering is a subset operation: every row in the filtered
   * output must exist in the original data.
   */
  it('PROPERTY: filtered output is always a subset of input data', () => {
    fc.assert(
      fc.property(
        fc.array(bookingArb, { minLength: 0, maxLength: 20 }),
        fc.record({
          reservationCode: filterStr,
          guestName: filterStr,
          channel: filterStr,
        }),
        (data, filterValues) => {
          vi.useFakeTimers();
          try {
            const { result } = renderHook(() =>
              useFilterableTable<Booking>(data, {
                initialFilters: STR_INITIAL_FILTERS,
                defaultSort: { field: 'checkinDate', direction: 'desc' },
              }),
            );

            act(() => {
              for (const [key, value] of Object.entries(filterValues)) {
                if (value !== '') result.current.setFilter(key, value);
              }
            });
            act(() => { vi.advanceTimersByTime(200); });

            const hookOutput = result.current.processedData;

            // Every row in output must be in original data
            for (const row of hookOutput) {
              expect(data).toContainEqual(row);
            }
            // Output can never be larger than input
            expect(hookOutput.length).toBeLessThanOrEqual(data.length);
          } finally {
            vi.useRealTimers();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
