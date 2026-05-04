/**
 * Example-based unit tests for CreditCardProcessor
 *
 * Tests specific examples and edge cases as defined in the spec.
 * @see .kiro/specs/FIN/credit-card-processing/tasks.md — Task 9
 */

import { processCreditCardTransactions } from '../CreditCardProcessor';
import type { LookupData, CreditCardAccount } from '../../BankingProcessor';

describe('CreditCardProcessor example-based tests', () => {
  const mockLookupData: LookupData = {
    accounts: ['2001', '4002'],
    descriptions: [],
    bank_accounts: [],
    credit_card_accounts: [
      {
        iban: 'NL80RABO0107936917',
        Account: '2001',
        card_number: '6416',
        administration: 'TestTenant',
      },
    ],
    exchange_rate_account: '4002',
  };

  const mockLookupDataNoFx: LookupData = {
    ...mockLookupData,
    exchange_rate_account: null,
  };

  describe('EUR expense transaction', () => {
    it('negative amount → TransactionAmount = absolute value, Credit = lookup Account, Debet = empty', () => {
      const csvRow = [
        'NL80RABO0107936917', // IBAN
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '-20,58', // Negative amount (expense)
        'Test purchase',
        '', '', '', // No foreign currency
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');

      expect(result.transactions).toHaveLength(1);
      const tx = result.transactions[0];

      expect(tx.TransactionAmount).toBe(20.58); // Absolute value
      expect(tx.Credit).toBe('2001'); // Lookup Account
      expect(tx.Debet).toBe(''); // Empty for expense
      expect(tx.Administration).toBe('TestTenant');
    });
  });

  describe('EUR credit transaction', () => {
    it('positive amount → Debet = lookup Account, Credit = empty', () => {
      const csvRow = [
        'NL80RABO0107936917', // IBAN
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '15,00', // Positive amount (credit)
        'Test refund',
        '', '', '', // No foreign currency
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');

      expect(result.transactions).toHaveLength(1);
      const tx = result.transactions[0];

      expect(tx.TransactionAmount).toBe(15.0);
      expect(tx.Debet).toBe('2001'); // Lookup Account
      expect(tx.Credit).toBe(''); // Empty for credit
    });
  });

  describe('Foreign currency transaction', () => {
    it('generates 2 transactions (main + exchange rate diff)', () => {
      const csvRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '100,00', // Settlement in EUR
        'Hotel booking',
        '125,00', // Original amount in USD (creates non-zero diff)
        'USD', // Original currency
        '1,20', // Exchange rate
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');

      expect(result.transactions).toHaveLength(2);

      const mainTx = result.transactions[0];
      const fxTx = result.transactions[1];

      // Main transaction
      expect(mainTx.TransactionAmount).toBe(100.0);
      expect(mainTx.Debet).toBe('2001'); // Credit transaction
      expect(mainTx.Credit).toBe('');

      // Exchange rate transaction
      // 125/1.2 = 104.1667, diff = 100 - 104.1667 = -4.1667 ≈ -4.17
      expect(fxTx.TransactionAmount).toBeCloseTo(4.17, 2);
      expect(fxTx.Debet).toBe('4002'); // Loss: Debet = exchange_rate_account
      expect(fxTx.Credit).toBe('');
      expect(fxTx.Ref2).toBe('REF123456_FX');
    });
  });

  describe('Header row detection', () => {
    it('row with columns[0] === "Tegenrekening IBAN" throws error (IBAN not found)', () => {
      const headerRow = [
        'Tegenrekening IBAN',
        'Munt',
        'Creditcard Nummer',
        'Productnaam',
        'Creditcard Regel1',
        'Creditcard Regel2',
        'Transactiereferentie',
        'Datum',
        'Bedrag',
        'Omschrijving',
        'Oorspr bedrag',
        'Oorspr munt',
        'Koers',
      ];

      // The function throws an error because the IBAN is not in the lookup
      expect(() => {
        processCreditCardTransactions(headerRow, 0, mockLookupData, 'CSV_CC_test.csv');
      }).toThrow('Tegenrekening IBAN');
    });
  });

  describe('Row validation', () => {
    it('row with < 13 columns returns empty result', () => {
      const shortRow = ['NL80RABO0107936917', 'EUR', '6416', 'Visa']; // Only 4 columns

      const result = processCreditCardTransactions(shortRow, 0, mockLookupData, 'CSV_CC_test.csv');
      expect(result.transactions).toHaveLength(0);
      expect(result.warnings).toHaveLength(0);
    });

    it('row with zero amount returns empty result', () => {
      const zeroAmountRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '0,00', // Zero amount
        'Test',
        '', '', '',
      ];

      const result = processCreditCardTransactions(zeroAmountRow, 0, mockLookupData, 'CSV_CC_test.csv');
      expect(result.transactions).toHaveLength(0);
      expect(result.warnings).toHaveLength(0);
    });
  });

  describe('Comma decimal parsing', () => {
    it('"-20,58" → amount 20.58', () => {
      const csvRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '-20,58',
        'Test',
        '', '', '',
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');
      expect(result.transactions[0].TransactionAmount).toBe(20.58);
    });
  });

  describe('Missing exchange rate account', () => {
    it('main transaction created, warning added, no FX transaction', () => {
      const csvRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '100,00',
        'Hotel booking',
        '125,00', // Creates non-zero diff
        'USD',
        '1,20',
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupDataNoFx, 'CSV_CC_test.csv');

      expect(result.transactions).toHaveLength(1); // Only main transaction
      expect(result.warnings).toHaveLength(1);
      expect(result.warnings[0]).toContain('Koersverschillenrekening niet geconfigureerd');
      expect(result.warnings[0]).toContain('4.17'); // Diff amount: 125/1.2 = 104.1667, diff = 100 - 104.1667 = -4.1667
    });
  });

  describe('Description building', () => {
    it('EUR transaction gets plain description', () => {
      const csvRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '-20,58',
        'Test purchase description',
        '', '', '',
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');
      expect(result.transactions[0].TransactionDescription).toBe('Test purchase description');
    });

    it('foreign transaction gets [USD 25,00] suffix', () => {
      const csvRow = [
        'NL80RABO0107936917',
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '20,00',
        'Hotel booking',
        '25,00',
        'USD',
        '1,25',
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');
      expect(result.transactions[0].TransactionDescription).toBe('Hotel booking [USD 25,00]');
    });
  });

  describe('IBAN not found', () => {
    it('throws Error with IBAN in message', () => {
      const csvRow = [
        'NL99UNKNOWN99999999', // Unknown IBAN
        'EUR',
        '6416',
        'Visa',
        'Cardholder',
        'Company',
        'REF123456',
        '2024-12-15',
        '-20,58',
        'Test',
        '', '', '',
      ];

      expect(() => {
        processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');
      }).toThrow('NL99UNKNOWN99999999');
    });
  });

  describe('Reference field mapping', () => {
    it('Ref1, Ref2, Ref3, Ref4 map to correct CSV columns', () => {
      const csvRow = [
        'NL80RABO0107936917', // Ref3
        'EUR',
        '6416',
        'ProductName', // Ref1
        'Cardholder',
        'Company',
        'TransactionRef', // Ref2
        '2024-12-15',
        '-20,58',
        'Test',
        '', '', '',
      ];

      const result = processCreditCardTransactions(csvRow, 0, mockLookupData, 'CSV_CC_test.csv');
      const tx = result.transactions[0];

      expect(tx.Ref1).toBe('ProductName'); // column 3
      expect(tx.Ref2).toBe('TransactionRef'); // column 6
      expect(tx.Ref3).toBe('NL80RABO0107936917'); // column 0
      expect(tx.Ref4).toBe('CSV_CC_test.csv'); // fileName
      expect(tx.ReferenceNumber).toBe(''); // Empty for pattern matcher
    });
  });
});