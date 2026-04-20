/**
 * Bug Condition Exploration Test — Revolut Dutch Status Filter
 *
 * Property 1: Non-completed Revolut transactions bypass filter
 *
 * CRITICAL: This test encodes the EXPECTED (correct) behavior.
 * On UNFIXED code it MUST FAIL — failure confirms the bug exists.
 * After the fix is applied, this same test validates the fix when it passes.
 *
 * Bug condition C(X): completionDate.trim() === '' OR saldo.trim() === ''
 * Expected behavior: processRevolutTransaction returns [] for all such inputs.
 *
 * Requirements: 1.1, 1.2, 1.4, 2.1, 2.2
 */
import fc from 'fast-check';
import { processRevolutTransaction } from '../components/BankingProcessor';

// Dutch header matching the Revolut CSV export format
const DUTCH_HEADER = [
  'Type', 'Product', 'Startdatum', 'Datum voltooid',
  'Beschrijving', 'Bedrag', 'Kosten', 'Valuta', 'Status', 'Saldo',
];

// English header for cross-language coverage
const ENGLISH_HEADER = [
  'Type', 'Product', 'Started Date', 'Completed Date',
  'Description', 'Amount', 'Fee', 'Currency', 'State', 'Balance',
];

// Minimal bankLookup matching the Revolut IBAN pattern used in production
const bankLookup = { Account: '1023', administration: 'PeterPrive' };

describe('Bug Condition Exploration — Revolut Dutch Status Filter', () => {
  // -----------------------------------------------------------------------
  // Concrete test cases (deterministic)
  // -----------------------------------------------------------------------

  it('should filter Dutch pending transaction (IN BEHANDELING, empty completion date + empty saldo)', () => {
    const columns = [
      'Kaartbetaling',       // 0  Type
      'Betaalrekening',      // 1  Product
      '2026-04-16 12:07:04', // 2  Startdatum
      '',                    // 3  Datum voltooid  ← EMPTY
      'Albert Heijn',        // 4  Beschrijving
      '-29.06',              // 5  Bedrag
      '0.00',                // 6  Kosten
      'EUR',                 // 7  Valuta
      'IN BEHANDELING',      // 8  Status
      '',                    // 9  Saldo           ← EMPTY
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
    expect(result).toEqual([]);
  });

  it('should filter Dutch declined transaction (GEWEIGERD, empty completion date + empty saldo)', () => {
    const columns = [
      'Kaartbetaling',
      'Betaalrekening',
      '2026-04-10 09:15:00',
      '',                    // Datum voltooid ← EMPTY
      'Bol.com',
      '-55.99',
      '0.00',
      'EUR',
      'GEWEIGERD',           // Dutch for "declined"
      '',                    // Saldo ← EMPTY
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
    expect(result).toEqual([]);
  });

  it('should filter when saldo is filled but completion date is empty', () => {
    const columns = [
      'Kaartbetaling',
      'Betaalrekening',
      '2026-04-12 14:30:00',
      '',                    // Datum voltooid ← EMPTY
      'Shell Station',
      '-45.00',
      '0.00',
      'EUR',
      'IN BEHANDELING',
      '1200.50',             // Saldo is filled
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
    expect(result).toEqual([]);
  });

  it('should filter when completion date is filled but saldo is empty', () => {
    const columns = [
      'Kaartbetaling',
      'Betaalrekening',
      '2026-04-12 14:30:00',
      '2026-04-12 15:00:00', // Datum voltooid is filled
      'Shell Station',
      '-45.00',
      '0.00',
      'EUR',
      'VOLTOOID',
      '',                    // Saldo ← EMPTY
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
    expect(result).toEqual([]);
  });

  it('should filter when both completion date and saldo are whitespace only', () => {
    const columns = [
      'Kaartbetaling',
      'Betaalrekening',
      '2026-04-12 14:30:00',
      '   ',                 // Datum voltooid ← whitespace only
      'Jumbo Supermarkt',
      '-22.50',
      '0.00',
      'EUR',
      'IN BEHANDELING',
      '  ',                  // Saldo ← whitespace only
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
    expect(result).toEqual([]);
  });

  // -----------------------------------------------------------------------
  // Property-based test (generative)
  // -----------------------------------------------------------------------

  it('PROPERTY: for all rows where completionDate is empty OR saldo is empty, result should be []', () => {
    // Arbitrary for a non-zero monetary amount (avoids the zero-amount filter)
    const nonZeroAmount = fc.oneof(
      fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => `-${v.toFixed(2)}`),
      fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => v.toFixed(2)),
    );

    // Arbitrary for an "empty-ish" string (empty or whitespace)
    const emptyish = fc.oneof(
      fc.constant(''),
      fc.constant('  '),
      fc.constant('   '),
    );

    // Arbitrary for a non-empty completion date
    const filledDate = fc.constant('2026-03-15 10:00:00');

    // Arbitrary for a non-empty saldo
    const filledSaldo = fc.double({ min: 0.01, max: 99999.99, noNaN: true }).map(v => v.toFixed(2));

    // Non-English status values that bypass the current REVERTED/PENDING check
    const nonEnglishStatus = fc.oneof(
      fc.constant('IN BEHANDELING'),
      fc.constant('GEWEIGERD'),
      fc.constant('TERUGGEDRAAID'),
      fc.constant('VOLTOOID'),           // even "completed" status — if fields are empty, should filter
      fc.constant('SOME_UNKNOWN_STATUS'),
    );

    const description = fc.oneof(
      fc.constant('Albert Heijn'),
      fc.constant('Bol.com'),
      fc.constant('Shell Station'),
      fc.string({ minLength: 1, maxLength: 30 }),
    );

    // Bug condition: completionDate empty OR saldo empty (at least one must be empty)
    const bugConditionRow = fc.tuple(
      description,
      nonZeroAmount,
      nonEnglishStatus,
      // Three variants: both empty, only completionDate empty, only saldo empty
      fc.oneof(
        fc.tuple(emptyish, emptyish),                // both empty
        fc.tuple(emptyish, filledSaldo),             // completionDate empty, saldo filled
        fc.tuple(filledDate, emptyish),              // completionDate filled, saldo empty
      ),
    ).map(([desc, amount, status, [completionDate, saldo]]) => [
      'Kaartbetaling',          // 0  Type
      'Betaalrekening',         // 1  Product
      '2026-04-16 12:07:04',   // 2  Startdatum
      completionDate,           // 3  Datum voltooid
      desc,                     // 4  Beschrijving
      amount,                   // 5  Bedrag
      '0.00',                   // 6  Kosten
      'EUR',                    // 7  Valuta
      status,                   // 8  Status
      saldo,                    // 9  Saldo
    ]);

    fc.assert(
      fc.property(bugConditionRow, (columns: string[]) => {
        const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
        // Bug condition holds → expected behavior is empty array
        expect(result).toEqual([]);
      }),
      { numRuns: 200 },
    );
  });
});
