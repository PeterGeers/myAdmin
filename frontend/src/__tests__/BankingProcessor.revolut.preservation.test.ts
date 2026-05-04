/**
 * Preservation Property Tests — Revolut Dutch Status Filter
 *
 * Property 2: Completed transactions produce correct output
 *
 * These tests capture the CURRENT (unfixed) behavior of processRevolutTransaction
 * for completed transactions. They must PASS on unfixed code to establish a baseline.
 * After the fix is applied, these tests ensure no regressions in completed transaction
 * processing (preservation checking).
 *
 * Observation-first methodology:
 *   Step 1 — Observe concrete behavior on unfixed code
 *   Step 2 — Write property-based tests capturing that behavior
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
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
const bankLookup = { Account: '1023', administration: 'PeterPrive', rekeningNummer: 'NL08REVO7549383472' };

// =========================================================================
// Step 1 — Observe behavior on UNFIXED code (concrete deterministic tests)
// =========================================================================

describe('Preservation — Observe current behavior on unfixed code', () => {
  it('completed Dutch row produces Transaction with correct amount and Ref2', () => {
    const columns = [
      'Kaartbetaling',          // 0  Type
      'Betaalrekening',         // 1  Product
      '2026-03-01 15:27:29',   // 2  Startdatum
      '2026-03-01 03:18:36',   // 3  Datum voltooid
      'Hotel Lelystad',         // 4  Beschrijving
      '-37.00',                 // 5  Bedrag
      '0.00',                   // 6  Kosten
      'EUR',                    // 7  Valuta
      'VOLTOOID',               // 8  Status
      '1290.32',                // 9  Saldo
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);

    expect(result).toHaveLength(1);
    expect(result[0].TransactionAmount).toBe(37.00);
    expect(result[0].TransactionDescription).toBe('Hotel Lelystad');
    expect(result[0].TransactionDate).toBe('2026-03-01');
    // Fixed Ref2 format: [beschrijving]_[saldo]_[datum voltooid]
    expect(result[0].Ref2).toBe('Hotel Lelystad_1290.32_2026-03-01 03:18:36');
    expect(result[0].Ref1).toBe('NL08REVO7549383472');
    expect(result[0].Credit).toBe('1023'); // negative amount → Credit
    expect(result[0].Debet).toBe('');
    expect(result[0].Ref3).toBe('1290.32');
    expect(result[0].Ref4).toBe('test.csv');
    expect(result[0].Administration).toBe('PeterPrive');
  });

  it('completed English row produces Transaction correctly', () => {
    const columns = [
      'Card payment',
      'Current',
      '2026-02-15 10:30:00',
      '2026-02-15 11:00:00',
      'Amazon UK',
      '-25.50',
      '0.00',
      'GBP',
      'COMPLETED',
      '850.75',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);

    expect(result).toHaveLength(1);
    expect(result[0].TransactionAmount).toBe(25.50);
    expect(result[0].TransactionDescription).toBe('Amazon UK');
    expect(result[0].TransactionDate).toBe('2026-02-15');
    // Fixed Ref2 format: [beschrijving]_[saldo]_[datum voltooid]
    expect(result[0].Ref2).toBe('Amazon UK_850.75_2026-02-15 11:00:00');
    expect(result[0].Credit).toBe('1023'); // negative amount → Credit
  });

  it('English REVERTED row returns []', () => {
    const columns = [
      'Card payment',
      'Current',
      '2026-02-10 08:00:00',
      '2026-02-10 09:00:00',
      'Refund Store',
      '-15.00',
      '0.00',
      'EUR',
      'REVERTED',
      '500.00',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);
    expect(result).toEqual([]);
  });

  it('English PENDING row returns []', () => {
    const columns = [
      'Card payment',
      'Current',
      '2026-04-16 12:07:04',
      '',
      'Some Shop',
      '-10.00',
      '0.00',
      'EUR',
      'PENDING',
      '',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);
    expect(result).toEqual([]);
  });

  it('zero-amount row (amount=0, fee=0) with filled completion date and saldo returns []', () => {
    const columns = [
      'Exchange',
      'Current',
      '2026-03-05 14:00:00',
      '2026-03-05 14:01:00',
      'Currency Exchange',
      '0.00',
      '0.00',
      'EUR',
      'COMPLETED',
      '1000.00',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);
    expect(result).toEqual([]);
  });

  it('fee transaction row (fee > 0) produces fee Transaction with Revo Charges Ref2', () => {
    const columns = [
      'Card payment',
      'Current',
      '2026-03-10 16:00:00',
      '2026-03-10 16:30:00',
      'Foreign Purchase',
      '-100.00',
      '1.50',
      'USD',
      'COMPLETED',
      '750.25',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);

    // Should have 2 transactions: main + fee
    expect(result).toHaveLength(2);

    // Main transaction
    expect(result[0].TransactionAmount).toBe(100.00);
    expect(result[0].TransactionDescription).toBe('Foreign Purchase');
    // Fixed Ref2 format: [beschrijving]_[saldo]_[datum voltooid]
    expect(result[0].Ref2).toBe('Foreign Purchase_750.25_2026-03-10 16:30:00');

    // Fee transaction
    expect(result[1].TransactionAmount).toBe(1.50);
    expect(result[1].TransactionDescription).toBe('Revo Charges');
    // Fixed Ref2 format for fees: Revo Charges_[saldo]_[datum voltooid]
    expect(result[1].Ref2).toBe('Revo Charges_750.25_2026-03-10 16:30:00');
    expect(result[1].Credit).toBe('1023');
    expect(result[1].Debet).toBe('');
  });

  it('positive amount transaction sets Debet (not Credit)', () => {
    const columns = [
      'Transfer',
      'Current',
      '2026-03-20 09:00:00',
      '2026-03-20 09:05:00',
      'Salary Deposit',
      '2500.00',
      '0.00',
      'EUR',
      'COMPLETED',
      '3500.00',
    ];

    const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);

    expect(result).toHaveLength(1);
    expect(result[0].TransactionAmount).toBe(2500.00);
    expect(result[0].Debet).toBe('1023'); // positive amount → Debet
    expect(result[0].Credit).toBe('');
  });
});

// =========================================================================
// Step 2 — Property-based tests capturing observed behavior
// =========================================================================

describe('Preservation — Property-based tests', () => {
  // -----------------------------------------------------------------------
  // Arbitraries (generators)
  // -----------------------------------------------------------------------

  // Generate a date string in the format used by Revolut CSVs
  const dateTimeArb = fc.tuple(
    fc.integer({ min: 2025, max: 2027 }),
    fc.integer({ min: 1, max: 12 }),
    fc.integer({ min: 1, max: 28 }),
    fc.integer({ min: 0, max: 23 }),
    fc.integer({ min: 0, max: 59 }),
    fc.integer({ min: 0, max: 59 }),
  ).map(([y, m, d, h, mi, s]) =>
    `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')} ` +
    `${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  );

  // Non-zero monetary amount as string (negative or positive, never zero)
  const nonZeroAmountArb = fc.oneof(
    fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => `-${v.toFixed(2)}`),
    fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => v.toFixed(2)),
  );

  // Saldo: a positive number formatted to 2 decimals (non-empty for completed transactions)
  const saldoArb = fc.double({ min: 0.01, max: 99999.99, noNaN: true }).map(v => v.toFixed(2));

  // Description: non-empty alphanumeric string (avoids special chars that could break Ref2 matching)
  const descriptionArb = fc.stringMatching(/^[A-Za-z0-9 ]{1,30}$/).filter(s => s.trim().length > 0);

  // Completed status values
  const completedStatusArb = fc.oneof(
    fc.constant('VOLTOOID'),
    fc.constant('COMPLETED'),
  );

  // Fee amount: zero string (no fee)
  const zeroFee = fc.constant('0.00');

  // Build a completed transaction row (both completion date and saldo filled)
  const completedRowArb = fc.tuple(
    dateTimeArb,       // startdatum
    dateTimeArb,       // datum voltooid
    descriptionArb,    // beschrijving
    nonZeroAmountArb,  // bedrag
    zeroFee,           // kosten (no fee for this property)
    completedStatusArb,// status
    saldoArb,          // saldo
  ).map(([startdatum, datumVoltooid, beschrijving, bedrag, kosten, status, saldo]) => ({
    columns: [
      'Kaartbetaling',   // 0  Type
      'Betaalrekening',  // 1  Product
      startdatum,        // 2  Startdatum
      datumVoltooid,     // 3  Datum voltooid
      beschrijving,      // 4  Beschrijving
      bedrag,            // 5  Bedrag
      kosten,            // 6  Kosten
      'EUR',             // 7  Valuta
      status,            // 8  Status
      saldo,             // 9  Saldo
    ],
    startdatum,
    datumVoltooid,
    beschrijving,
    bedrag,
    saldo,
  }));

  // -----------------------------------------------------------------------
  // Property: completed rows produce non-empty Transaction[] with correct fields
  // -----------------------------------------------------------------------

  it('PROPERTY: completed rows produce Transaction[] with correct amount, date, and Ref2 format', () => {
    fc.assert(
      fc.property(completedRowArb, ({ columns, startdatum, datumVoltooid, beschrijving, bedrag, saldo }) => {
        const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);

        // Must produce at least one transaction
        expect(result.length).toBeGreaterThanOrEqual(1);

        const tx = result[0];
        const expectedAmount = Math.abs(parseFloat(bedrag.replace(',', '.')));
        const expectedSaldo = parseFloat(saldo.replace(',', '.')).toFixed(2);
        const expectedDate = startdatum.split(' ')[0];
        // Fixed Ref2 format: [beschrijving]_[saldo]_[datum voltooid]
        const expectedRef2 = `${beschrijving}_${expectedSaldo}_${datumVoltooid}`;

        expect(tx.TransactionAmount).toBeCloseTo(expectedAmount, 2);
        expect(tx.TransactionDate).toBe(expectedDate);
        expect(tx.Ref2).toBe(expectedRef2);
        expect(tx.TransactionDescription).toBe(beschrijving);
        expect(tx.Ref1).toBe('NL08REVO7549383472');
        expect(tx.Ref4).toBe('test.csv');
        expect(tx.Administration).toBe('PeterPrive');

        // Debet/Credit correctness
        const amount = parseFloat(bedrag.replace(',', '.'));
        if (amount < 0) {
          expect(tx.Credit).toBe('1023');
          expect(tx.Debet).toBe('');
        } else {
          expect(tx.Debet).toBe('1023');
          expect(tx.Credit).toBe('');
        }
      }),
      { numRuns: 200 },
    );
  });

  // -----------------------------------------------------------------------
  // Property: REVERTED / PENDING status rows return []
  // -----------------------------------------------------------------------

  it('PROPERTY: rows with REVERTED or PENDING status return []', () => {
    const revertedPendingStatus = fc.oneof(
      fc.constant('REVERTED'),
      fc.constant('PENDING'),
    );

    const statusFilterRow = fc.tuple(
      dateTimeArb,
      dateTimeArb,
      descriptionArb,
      nonZeroAmountArb,
      saldoArb,
      revertedPendingStatus,
    ).map(([startdatum, datumVoltooid, beschrijving, bedrag, saldo, status]) => [
      'Card payment',
      'Current',
      startdatum,
      datumVoltooid,
      beschrijving,
      bedrag,
      '0.00',
      'EUR',
      status,
      saldo,
    ]);

    fc.assert(
      fc.property(statusFilterRow, (columns: string[]) => {
        const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);
        expect(result).toEqual([]);
      }),
      { numRuns: 200 },
    );
  });

  // -----------------------------------------------------------------------
  // Property: zero-amount rows (amount=0 AND fee=0) return []
  // -----------------------------------------------------------------------

  it('PROPERTY: rows where amount=0 and fee=0 return []', () => {
    const zeroAmountRow = fc.tuple(
      dateTimeArb,
      dateTimeArb,
      descriptionArb,
      completedStatusArb,
      saldoArb,
    ).map(([startdatum, datumVoltooid, beschrijving, status, saldo]) => [
      'Exchange',
      'Current',
      startdatum,
      datumVoltooid,
      beschrijving,
      '0.00',       // amount = 0
      '0.00',       // fee = 0
      'EUR',
      status,
      saldo,
    ]);

    fc.assert(
      fc.property(zeroAmountRow, (columns: string[]) => {
        const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', DUTCH_HEADER);
        expect(result).toEqual([]);
      }),
      { numRuns: 100 },
    );
  });

  // -----------------------------------------------------------------------
  // Property: fee > 0 produces a fee Transaction with 'Revo Charges'
  // -----------------------------------------------------------------------

  it('PROPERTY: rows with fee > 0 include a fee Transaction with Revo Charges', () => {
    const positiveFee = fc.double({ min: 0.01, max: 50.00, noNaN: true }).map(v => v.toFixed(2));

    const feeRowArb = fc.tuple(
      dateTimeArb,
      dateTimeArb,
      descriptionArb,
      nonZeroAmountArb,
      positiveFee,
      completedStatusArb,
      saldoArb,
    ).map(([startdatum, datumVoltooid, beschrijving, bedrag, kosten, status, saldo]) => ({
      columns: [
        'Card payment',
        'Current',
        startdatum,
        datumVoltooid,
        beschrijving,
        bedrag,
        kosten,
        'EUR',
        status,
        saldo,
      ],
      startdatum,
      datumVoltooid,
      saldo,
      kosten,
    }));

    fc.assert(
      fc.property(feeRowArb, ({ columns, startdatum, datumVoltooid, saldo, kosten }) => {
        const result = processRevolutTransaction(columns, 0, bankLookup, 'test.csv', ENGLISH_HEADER);

        // Must have at least 2 transactions (main + fee)
        expect(result.length).toBeGreaterThanOrEqual(2);

        // Find the fee transaction
        const feeTx = result.find(t => t.TransactionDescription === 'Revo Charges');
        expect(feeTx).toBeDefined();

        const expectedFee = parseFloat(kosten.replace(',', '.'));
        const expectedSaldo = parseFloat(saldo.replace(',', '.')).toFixed(2);
        // Fixed Ref2 format for fees: Revo Charges_[saldo]_[datum voltooid]
        const expectedFeeRef2 = `Revo Charges_${expectedSaldo}_${datumVoltooid}`;

        expect(feeTx!.TransactionAmount).toBeCloseTo(expectedFee, 2);
        expect(feeTx!.Ref2).toBe(expectedFeeRef2);
        expect(feeTx!.TransactionDescription).toBe('Revo Charges');
        expect(feeTx!.Credit).toBe('1023'); // fee is always a credit
        expect(feeTx!.Debet).toBe('');
      }),
      { numRuns: 200 },
    );
  });
});
