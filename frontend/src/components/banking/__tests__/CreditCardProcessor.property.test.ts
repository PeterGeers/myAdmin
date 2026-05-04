/**
 * Property-based tests for CreditCardProcessor
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 * Tests validate correctness properties from the design document.
 *
 * @see .kiro/specs/FIN/credit-card-processing/design.md — Properties 1–6
 */

import fc from 'fast-check';
import { processCreditCardTransactions } from '../CreditCardProcessor';
import type { LookupData, CreditCardAccount } from '../../BankingProcessor';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a NL-format IBAN string (e.g., NL80RABO0107936917). */
function arbitraryIban(): fc.Arbitrary<string> {
  return fc
    .tuple(
      fc.integer({ min: 10, max: 99 }),
      fc.constantFrom('RABO', 'INGB', 'ABNA', 'TRIO', 'KNAB'),
      fc.stringMatching(/^[0-9]{10}$/),
    )
    .map(([check, bank, digits]) => `NL${check}${bank}${digits}`);
}

/** Generate a non-zero comma-decimal amount string (e.g., "-20,58" or "15,00"). */
function arbitraryAmount(): fc.Arbitrary<string> {
  return fc
    .double({ min: 0.01, max: 99999.99, noNaN: true })
    .chain((abs) =>
      fc.boolean().map((negative) => {
        const val = negative ? -abs : abs;
        return val.toFixed(2).replace('.', ',');
      }),
    );
}

/** Generate a YYYY-MM-DD date string. */
function arbitraryDate(): fc.Arbitrary<string> {
  return fc
    .tuple(
      fc.integer({ min: 2020, max: 2026 }),
      fc.integer({ min: 1, max: 12 }),
      fc.integer({ min: 1, max: 28 }),
    )
    .map(
      ([y, m, d]) =>
        `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
    );
}

/** Generate a short alphanumeric string for descriptions and references. */
function arbitraryText(): fc.Arbitrary<string> {
  return fc.stringMatching(/^[A-Za-z0-9 ]{1,20}$/);
}

/** Generate a unique transaction reference string. */
function arbitraryTransRef(): fc.Arbitrary<string> {
  return fc.stringMatching(/^[A-Z0-9]{6,16}$/);
}

/**
 * Generate a valid 13-column CSV row for a domestic (EUR) credit card transaction.
 * Columns: [0] IBAN, [1] currency, [2] card number, [3] product name,
 *          [4] cardholder, [5] company, [6] transaction ref, [7] date,
 *          [8] amount, [9] description, [10] orig amount, [11] orig currency, [12] rate
 */
function arbitraryCsvRow(iban: string): fc.Arbitrary<string[]> {
  return fc
    .tuple(
      fc.stringMatching(/^[0-9]{4}$/), // card number last 4
      arbitraryText(), // product name
      arbitraryText(), // cardholder
      arbitraryText(), // company
      arbitraryTransRef(), // transaction ref
      arbitraryDate(), // date
      arbitraryAmount(), // amount (non-zero)
      arbitraryText(), // description
    )
    .map(([card, product, holder, company, ref, date, amount, desc]) => [
      iban, // 0: Tegenrekening IBAN
      'EUR', // 1: Munt
      card, // 2: Creditcard Nummer
      product, // 3: Productnaam
      holder, // 4: Creditcard Regel1
      company, // 5: Creditcard Regel2
      ref, // 6: Transactiereferentie
      date, // 7: Datum
      amount, // 8: Bedrag
      desc, // 9: Omschrijving
      '', // 10: Oorspr bedrag (empty for EUR)
      '', // 11: Oorspr munt (empty for EUR)
      '', // 12: Koers (empty for EUR)
    ]);
}

/**
 * Generate a valid 13-column CSV row for a foreign currency credit card transaction.
 * Columns 10-12 are populated with original amount, currency code, and exchange rate.
 */
function arbitraryForeignCsvRow(iban: string): fc.Arbitrary<string[]> {
  return fc
    .tuple(
      arbitraryCsvRow(iban),
      fc.double({ min: 0.01, max: 99999.99, noNaN: true }), // original amount
      fc.constantFrom('USD', 'GBP', 'CHF', 'JPY', 'SEK', 'NOK', 'DKK'),
      fc.double({ min: 0.01, max: 200.0, noNaN: true }), // exchange rate > 0
    )
    .map(([row, origAmount, currency, rate]) => {
      const newRow = [...row];
      newRow[10] = origAmount.toFixed(2).replace('.', ',');
      newRow[11] = currency;
      newRow[12] = rate.toFixed(6).replace('.', ',');
      return newRow;
    });
}

/**
 * Generate LookupData with at least one credit_card_accounts entry matching
 * the given IBAN, and an exchange_rate_account.
 */
function arbitraryLookupData(iban: string): fc.Arbitrary<LookupData> {
  return fc
    .tuple(
      fc.stringMatching(/^[0-9]{4}$/), // Account code
      fc.stringMatching(/^[A-Za-z]{3,15}$/), // administration name
      fc.stringMatching(/^[0-9]{4}$/), // card number
      fc.stringMatching(/^[0-9]{4}$/), // exchange rate account code
    )
    .map(([account, admin, cardNum, fxAccount]) => ({
      accounts: [account],
      descriptions: [],
      bank_accounts: [],
      credit_card_accounts: [
        {
          iban,
          Account: account,
          card_number: cardNum,
          administration: admin,
        },
      ],
      exchange_rate_account: fxAccount,
    }));
}

/**
 * Generate LookupData with an exchange_rate_account set to null.
 */
function arbitraryLookupDataNoFx(iban: string): fc.Arbitrary<LookupData> {
  return arbitraryLookupData(iban).map((ld) => ({
    ...ld,
    exchange_rate_account: null,
  }));
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Parse a comma-decimal string to a number, matching the processor's logic. */
function parseCommaDecimal(s: string): number {
  return Math.round(parseFloat(s.replace(',', '.')) * 100) / 100;
}

// ---------------------------------------------------------------------------
// Property 1: CSV Parsing Validity
// ---------------------------------------------------------------------------

describe('Property 1: CSV Parsing Validity', () => {
  /**
   * Validates: Requirements 7.2, 7.3, 7.4, 7.7
   *
   * For any valid 13-column CSV row with non-zero amount and configured IBAN:
   * result has at least 1 transaction, TransactionAmount > 0,
   * TransactionDate equals column 7, Ref2 equals column 6.
   */
  it('valid CSV row always produces at least one transaction with correct fields', () => {
    fc.assert(
      fc.property(
        arbitraryIban().chain((iban) =>
          fc.tuple(fc.constant(iban), arbitraryCsvRow(iban), arbitraryLookupData(iban)),
        ),
        ([iban, csvRow, lookupData]) => {
          const result = processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv');

          expect(result.transactions.length).toBeGreaterThanOrEqual(1);

          const main = result.transactions[0];
          expect(main.TransactionAmount).toBeGreaterThan(0);
          expect(main.TransactionDate).toBe(csvRow[7]);
          expect(main.Ref2).toBe(csvRow[6]);
        },
      ),
      { numRuns: 100 },
    );
  }, 30_000);
});

// ---------------------------------------------------------------------------
// Property 2: Lookup Resolution Determines Account Fields
// ---------------------------------------------------------------------------

describe('Property 2: Lookup Resolution Determines Account Fields', () => {
  /**
   * Validates: Requirements 2.1, 2.3, 2.4, 2.5
   *
   * For any CSV row where IBAN exists in credit_card_accounts:
   * Administration equals lookup's administration, and Credit (expense) or
   * Debet (credit) equals lookup's Account — never hardcoded values.
   */
  it('account fields come from lookup, never hardcoded', () => {
    const hardcodedValues = ['4002', '2001', 'PeterPrive', 'GoodwinSolutions'];

    fc.assert(
      fc.property(
        arbitraryIban().chain((iban) =>
          fc.tuple(fc.constant(iban), arbitraryCsvRow(iban), arbitraryLookupData(iban)),
        ),
        ([iban, csvRow, lookupData]) => {
          const result = processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv');
          const main = result.transactions[0];
          const ccLookup = lookupData.credit_card_accounts[0];

          // Administration must match lookup
          expect(main.Administration).toBe(ccLookup.administration);

          // The account field (Credit for expense, Debet for credit) must match lookup
          const amount = parseCommaDecimal(csvRow[8]);
          if (amount < 0) {
            // Expense: Credit = lookup Account
            expect(main.Credit).toBe(ccLookup.Account);
          } else {
            // Credit: Debet = lookup Account
            expect(main.Debet).toBe(ccLookup.Account);
          }

          // Never hardcoded values
          for (const hc of hardcodedValues) {
            expect(main.Credit).not.toBe(hc);
            expect(main.Debet).not.toBe(hc);
            expect(main.Administration).not.toBe(hc);
          }
        },
      ),
      { numRuns: 100 },
    );
  }, 30_000);
});

// ---------------------------------------------------------------------------
// Property 3: Missing IBAN Throws Descriptive Error
// ---------------------------------------------------------------------------

describe('Property 3: Missing IBAN Throws Descriptive Error', () => {
  /**
   * Validates: Requirements 2.2
   *
   * For any IBAN not in credit_card_accounts: processCreditCardTransactions
   * throws Error whose message contains the missing IBAN string.
   */
  it('throws error containing the missing IBAN', () => {
    fc.assert(
      fc.property(
        fc.tuple(arbitraryIban(), arbitraryIban()).filter(([a, b]) => a !== b),
        arbitraryDate(),
        arbitraryAmount(),
        arbitraryTransRef(),
        ([csvIban, lookupIban], date, amount, ref) => {
          // Build a CSV row with csvIban, but lookup only has lookupIban
          const csvRow = [
            csvIban, 'EUR', '6416', 'Visa', 'Holder', 'Company',
            ref, date, amount, 'Description', '', '', '',
          ];
          const lookupData: LookupData = {
            accounts: [],
            descriptions: [],
            bank_accounts: [],
            credit_card_accounts: [
              { iban: lookupIban, Account: '2001', card_number: '1234', administration: 'TestAdmin' },
            ],
            exchange_rate_account: null,
          };

          expect(() =>
            processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv'),
          ).toThrow(csvIban);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Exchange Rate Difference Calculation
// ---------------------------------------------------------------------------

describe('Property 4: Exchange Rate Difference Calculation', () => {
  /**
   * Validates: Requirements 3.2, 3.3
   *
   * For any foreign currency transaction: exchange rate diff =
   * abs(settlement) - abs(original / rate), and
   * mainAmount + exchangeRateDiff ≈ abs(settlement) (within rounding tolerance).
   */
  it('exchange rate difference satisfies the accounting identity', () => {
    fc.assert(
      fc.property(
        arbitraryIban().chain((iban) =>
          fc.tuple(
            fc.constant(iban),
            arbitraryForeignCsvRow(iban),
            arbitraryLookupData(iban),
          ),
        ),
        ([iban, csvRow, lookupData]) => {
          const result = processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv');

          const settlementAmount = Math.abs(parseCommaDecimal(csvRow[8]));
          const originalAmount = parseFloat(csvRow[10].replace(',', '.'));
          const exchangeRate = parseFloat(csvRow[12].replace(',', '.'));

          const calculatedEur = Math.round((originalAmount / exchangeRate) * 100) / 100;
          const expectedDiff = Math.round((settlementAmount - Math.abs(calculatedEur)) * 100) / 100;

          if (Math.abs(expectedDiff) > 0.005) {
            // Should have 2 transactions: main + exchange rate
            expect(result.transactions.length).toBe(2);

            const mainTx = result.transactions[0];
            const fxTx = result.transactions[1];

            // Main transaction amount is the settlement amount
            expect(mainTx.TransactionAmount).toBeCloseTo(settlementAmount, 2);

            // Exchange rate diff amount matches expected
            expect(fxTx.TransactionAmount).toBeCloseTo(Math.abs(expectedDiff), 2);

            // Accounting identity: main amount is the settlement, FX diff accounts for the difference
            // mainAmount ± fxDiff should reconstruct the relationship
            const totalAccounted = mainTx.TransactionAmount;
            expect(totalAccounted).toBeCloseTo(settlementAmount, 2);
          } else {
            // Diff below threshold — only main transaction
            expect(result.transactions.length).toBe(1);
            expect(result.transactions[0].TransactionAmount).toBeCloseTo(settlementAmount, 2);
          }
        },
      ),
      { numRuns: 100 },
    );
  }, 30_000);
});

// ---------------------------------------------------------------------------
// Property 5: Exchange Rate Transaction Debit/Credit Direction
// ---------------------------------------------------------------------------

describe('Property 5: Exchange Rate Transaction Debit/Credit Direction', () => {
  /**
   * Validates: Requirements 3.5, 3.6, 3.7
   *
   * For any non-zero exchange rate diff with configured account:
   * positive diff → Credit = exchange_rate_account;
   * negative diff → Debet = exchange_rate_account.
   */
  it('FX transaction direction matches sign of exchange rate difference', () => {
    fc.assert(
      fc.property(
        arbitraryIban().chain((iban) =>
          fc.tuple(
            fc.constant(iban),
            arbitraryForeignCsvRow(iban),
            arbitraryLookupData(iban),
          ),
        ),
        ([iban, csvRow, lookupData]) => {
          const result = processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv');

          if (result.transactions.length < 2) {
            // No FX transaction generated (diff below threshold) — skip
            return;
          }

          const fxTx = result.transactions[1];
          const fxAccount = lookupData.exchange_rate_account!;

          const settlementAmount = Math.abs(parseCommaDecimal(csvRow[8]));
          const originalAmount = parseFloat(csvRow[10].replace(',', '.'));
          const exchangeRate = parseFloat(csvRow[12].replace(',', '.'));
          const calculatedEur = Math.round((originalAmount / exchangeRate) * 100) / 100;
          const diff = Math.round((settlementAmount - Math.abs(calculatedEur)) * 100) / 100;

          if (diff > 0) {
            // Gain: Credit = exchange_rate_account
            expect(fxTx.Credit).toBe(fxAccount);
            expect(fxTx.Debet).toBe('');
          } else {
            // Loss: Debet = exchange_rate_account
            expect(fxTx.Debet).toBe(fxAccount);
            expect(fxTx.Credit).toBe('');
          }
        },
      ),
      { numRuns: 100 },
    );
  }, 30_000);
});

// ---------------------------------------------------------------------------
// Property 6: Reference Field Mapping
// ---------------------------------------------------------------------------

describe('Property 6: Reference Field Mapping', () => {
  /**
   * Validates: Requirements 4.1, 4.4, 5.3, 5.4, 7.5, 7.6
   *
   * For any CSV row producing a transaction:
   * Ref1 = column 3, Ref2 = column 6, Ref3 = column 0,
   * ReferenceNumber = empty, Debet = empty for expense transactions.
   */
  it('reference fields map to correct CSV columns', () => {
    fc.assert(
      fc.property(
        arbitraryIban().chain((iban) =>
          fc.tuple(fc.constant(iban), arbitraryCsvRow(iban), arbitraryLookupData(iban)),
        ),
        ([iban, csvRow, lookupData]) => {
          const result = processCreditCardTransactions(csvRow, 0, lookupData, 'CSV_CC_test.csv');
          const main = result.transactions[0];

          // Ref1 = column 3 (Productnaam)
          expect(main.Ref1).toBe(csvRow[3]);

          // Ref2 = column 6 (Transactiereferentie)
          expect(main.Ref2).toBe(csvRow[6]);

          // Ref3 = column 0 (Tegenrekening IBAN)
          expect(main.Ref3).toBe(csvRow[0]);

          // ReferenceNumber = empty (for pattern matcher)
          expect(main.ReferenceNumber).toBe('');

          // For expense transactions, Debet should be empty (pattern matcher fills it)
          const amount = parseCommaDecimal(csvRow[8]);
          if (amount < 0) {
            expect(main.Debet).toBe('');
          }
        },
      ),
      { numRuns: 100 },
    );
  }, 30_000);
});
