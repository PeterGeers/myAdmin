/**
 * Unit tests for the FIN report CSV mapping helpers (mutatiesCsv.ts).
 *
 * These are pure helpers, so no React tree is rendered. The tests pin:
 *  - the fixed header order [date, reference, description, amount, debit,
 *    credit, administration];
 *  - the Debit = Reknum (account code) / Credit = AccountName (account name)
 *    contract and overall cell order;
 *  - RAW value pass-through (numeric Amount preserved, no locale formatting).
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 6.2, 8.1
 */

import { mutatiesCsvHeaders, mapMutatiesRow, MutatiesCsvRow } from './mutatiesCsv';

const labels = {
  date: 'Date',
  reference: 'Reference',
  description: 'Description',
  amount: 'Amount',
  debit: 'Debit',
  credit: 'Credit',
  administration: 'Administration',
};

const sampleRow: MutatiesCsvRow = {
  TransactionDate: '2024-01-15',
  ReferenceNumber: 'REF001',
  TransactionDescription: 'Test Transaction 1',
  Amount: 100.5,
  Reknum: '1000', // account code -> Debit
  AccountName: 'Test Account 1', // account name -> Credit
  Administration: 'TestTenant',
};

describe('mutatiesCsvHeaders', () => {
  it('returns the fixed column order: date, reference, description, amount, debit, credit, administration', () => {
    // Requirements: 5.3, 8.1
    expect(mutatiesCsvHeaders(labels)).toEqual([
      'Date',
      'Reference',
      'Description',
      'Amount',
      'Debit',
      'Credit',
      'Administration',
    ]);
  });

  it('emits exactly seven columns', () => {
    expect(mutatiesCsvHeaders(labels)).toHaveLength(7);
  });
});

describe('mapMutatiesRow', () => {
  it('sets Debit (index 4) to the account code (Reknum)', () => {
    // Property 5 — Validates: Requirements 5.1, 5.2, 5.4, 6.2
    expect(mapMutatiesRow(sampleRow)[4]).toBe(sampleRow.Reknum);
  });

  it('sets Credit (index 5) to the account name (AccountName)', () => {
    // Property 5 — Validates: Requirements 5.1, 5.2, 5.4, 6.2
    expect(mapMutatiesRow(sampleRow)[5]).toBe(sampleRow.AccountName);
  });

  it('returns cells in the same order as the headers', () => {
    // Requirements: 5.3, 8.1 — cell order must match mutatiesCsvHeaders order.
    expect(mapMutatiesRow(sampleRow)).toEqual([
      '2024-01-15', // date
      'REF001', // reference
      'Test Transaction 1', // description
      100.5, // amount (raw numeric)
      '1000', // debit = Reknum (account code)
      'Test Account 1', // credit = AccountName (account name)
      'TestTenant', // administration
    ]);
  });

  it('preserves the raw numeric Amount (no locale/currency formatting)', () => {
    // Requirements: 5.4 — raw values, no formatCurrency.
    const amountCell = mapMutatiesRow(sampleRow)[3];
    expect(amountCell).toBe(100.5);
    expect(typeof amountCell).toBe('number');
  });

  it('preserves a negative Amount as a raw number', () => {
    // Requirements: 5.4 — raw values, no sign/locale rewriting.
    const negativeRow: MutatiesCsvRow = { ...sampleRow, Amount: -50.25 };
    const amountCell = mapMutatiesRow(negativeRow)[3];
    expect(amountCell).toBe(-50.25);
    expect(typeof amountCell).toBe('number');
  });

  it('passes the raw TransactionDate string through unchanged (no formatDate)', () => {
    // Requirements: 5.4 — raw date string, no locale date output.
    expect(mapMutatiesRow(sampleRow)[0]).toBe('2024-01-15');
  });

  it('does not swap Debit and Credit', () => {
    // Guards against the inverse mapping (Debit=name, Credit=code).
    const cells = mapMutatiesRow(sampleRow);
    expect(cells[4]).not.toBe(sampleRow.AccountName);
    expect(cells[5]).not.toBe(sampleRow.Reknum);
  });
});
