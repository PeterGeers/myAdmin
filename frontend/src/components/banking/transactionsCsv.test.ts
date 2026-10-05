/**
 * Unit tests for the Transactions table CSV helper (Part a).
 *
 * Targets the pure helpers in transactionsCsv.ts without rendering React/Chakra.
 * Escaping/encoding is delegated to the shared csvExport util (the escaping
 * implementation under test here) — these tests pin the column contract, raw
 * value mapping, full-dataset export, order preservation, RFC-4180 escaping,
 * and the filename format.
 *
 * Feature: transactions-export
 * Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 4.1, 4.2
 */

import {
  transactionsCsvColumns,
  buildTransactionsCsv,
  transactionsCsvFilename,
  type CsvColumn,
} from './transactionsCsv';

// Headers mirror the resolved i18n labels; the pure builder is
// translation-agnostic, so fixed strings are sufficient here.
const HEADERS = {
  trxNumber: 'Trx Number',
  date: 'Date',
  description: 'Description',
  amount: 'Amount',
  debit: 'Debit',
  credit: 'Credit',
  reference: 'Reference',
  administration: 'Administration',
};

const ORDERED_HEADER_LINE =
  'Trx Number,Date,Description,Amount,Debit,Credit,Reference,Administration';

/** A representative raw transaction row (raw field values, no formatting). */
function sampleRow(overrides: Record<string, any> = {}): Record<string, any> {
  return {
    TransactionNumber: 1001,
    TransactionDate: '2026-02-03',
    TransactionDescription: 'Office supplies',
    TransactionAmount: 1234.56,
    Debet: '4000',
    Credit: '1600',
    ReferenceNumber: 'REF-1',
    Administration: 'HDCN',
    ...overrides,
  };
}

describe('transactionsCsvColumns', () => {
  it('returns the ordered 8-column config mapping UI labels to raw fields', () => {
    const columns = transactionsCsvColumns(HEADERS);

    expect(columns).toHaveLength(8);
    expect(columns.map((c) => c.key)).toEqual([
      'TransactionNumber',
      'TransactionDate',
      'TransactionDescription',
      'TransactionAmount',
      'Debet',
      'Credit',
      'ReferenceNumber',
      'Administration',
    ]);
    expect(columns.map((c) => c.header)).toEqual([
      'Trx Number',
      'Date',
      'Description',
      'Amount',
      'Debit',
      'Credit',
      'Reference',
      'Administration',
    ]);
  });
});

describe('buildTransactionsCsv', () => {
  // Property 1 — Validates: Requirements 2.1, 2.4, 3.3
  describe('Property 1: mapping completeness and raw values', () => {
    it('emits the header line equal to the configured headers in order', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const csv = buildTransactionsCsv(columns, [sampleRow()]);
      const lines = csv.split('\n');

      expect(lines[0]).toBe(ORDERED_HEADER_LINE);
    });

    it('includes all 8 columns in order for every data line', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const rows = [sampleRow({ TransactionNumber: 1 }), sampleRow({ TransactionNumber: 2 })];
      const csv = buildTransactionsCsv(columns, rows);
      const lines = csv.split('\n');

      expect(lines).toHaveLength(3); // 1 header + 2 data
      for (const line of lines.slice(1)) {
        // No special chars in sampleRow, so a plain comma split yields 8 cells.
        expect(line.split(',')).toHaveLength(8);
      }
    });

    it('emits raw values with no €, thousands separators, or locale date output', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const row = sampleRow({ TransactionAmount: 1234567.89, TransactionDate: '2026-12-31' });
      const csv = buildTransactionsCsv(columns, [row]);
      const dataCells = csv.split('\n')[1].split(',');

      // Amount cell (index 3) is String(raw) — no currency symbol / grouping.
      expect(dataCells[3]).toBe(String(1234567.89));
      expect(dataCells[3]).toBe('1234567.89');
      expect(csv).not.toContain('€');
      expect(csv).not.toContain('1,234,567'); // no thousands grouping
      // Date cell (index 1) is the raw string, not a toLocaleDateString rendering.
      expect(dataCells[1]).toBe('2026-12-31');
    });
  });

  // Property 2 — Validates: Requirements 2.2
  describe('Property 2: full dataset, independent of display limit', () => {
    it('produces exactly N data lines + 1 header for N greater than any display limit', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const rows = Array.from({ length: 250 }, (_, i) =>
        sampleRow({ TransactionNumber: i + 1 }),
      );
      const csv = buildTransactionsCsv(columns, rows);
      const lines = csv.split('\n');

      expect(lines).toHaveLength(251); // 250 data + 1 header
      expect(lines.length - 1).toBe(250);
    });
  });

  // Property 3 — Validates: Requirements 2.3
  describe('Property 3: preserves input (sort) order', () => {
    it('keeps the TransactionNumber column sequence equal to input order', () => {
      const columns = transactionsCsvColumns(HEADERS);
      // Deterministic shuffle of distinct transaction numbers.
      const shuffled = [5, 2, 9, 1, 7, 3, 8, 4, 6, 0];
      const rows = shuffled.map((n) => sampleRow({ TransactionNumber: n }));
      const csv = buildTransactionsCsv(columns, rows);
      const dataLines = csv.split('\n').slice(1);

      // TransactionNumber is the first column (index 0).
      const emittedSequence = dataLines.map((line) => Number(line.split(',')[0]));
      expect(emittedSequence).toEqual(shuffled);
    });
  });

  // Property 4 — Validates: Requirements 4.1, 4.2
  describe('Property 4: RFC-4180 escaping delegated to the shared util', () => {
    it('quotes a field containing a comma', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const row = sampleRow({ TransactionDescription: 'Hello, World' });
      const csv = buildTransactionsCsv(columns, [row]);

      expect(csv).toContain('"Hello, World"');
    });

    it('quotes a field with an embedded double quote and doubles the quote', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const row = sampleRow({ TransactionDescription: 'Say "hi"' });
      const csv = buildTransactionsCsv(columns, [row]);

      // Internal quotes doubled, whole field wrapped in quotes.
      expect(csv).toContain('"Say ""hi"""');
    });

    it('quotes a field containing a newline', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const row = sampleRow({ TransactionDescription: 'Line1\nLine2' });
      const csv = buildTransactionsCsv(columns, [row]);

      expect(csv).toContain('"Line1\nLine2"');
    });

    it('maps null/undefined raw values to empty cells', () => {
      const columns = transactionsCsvColumns(HEADERS);
      const row = sampleRow({ ReferenceNumber: null, Administration: undefined });
      const csv = buildTransactionsCsv(columns, [row]);
      const dataCells = csv.split('\n')[1].split(',');

      expect(dataCells[6]).toBe(''); // ReferenceNumber
      expect(dataCells[7]).toBe(''); // Administration
    });
  });

  it('emits a header-only CSV when there are no rows', () => {
    const columns = transactionsCsvColumns(HEADERS);
    const csv = buildTransactionsCsv(columns, []);

    expect(csv).toBe(ORDERED_HEADER_LINE);
  });
});

describe('transactionsCsvFilename', () => {
  it('formats as transactions-YYYY-MM-DD.csv for an injected fixed date', () => {
    // Construct a local-time date so getFullYear/getMonth/getDate are stable
    // regardless of the runner timezone.
    const fixed = new Date(2026, 1, 3); // 2026-02-03 (month is 0-indexed)
    expect(transactionsCsvFilename(fixed)).toBe('transactions-2026-02-03.csv');
  });

  it('zero-pads single-digit months and days', () => {
    const fixed = new Date(2026, 0, 9); // 2026-01-09
    expect(transactionsCsvFilename(fixed)).toBe('transactions-2026-01-09.csv');
  });
});

// Type-level sanity: CsvColumn is exported and shaped as expected.
const _typeCheck: CsvColumn = { key: 'TransactionNumber', header: 'Trx Number' };
void _typeCheck;
