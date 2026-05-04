/**
 * Bug Condition Exploration Test — Bank Account Lookup Hardcoded Fallbacks
 *
 * Property 1: Bug Condition — Inconsistent Bank Account Resolution
 *
 * CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bug exists.
 * DO NOT attempt to fix the test or the code when it fails.
 *
 * Bug condition: processRevolutTransaction uses hardcoded IBAN 'NL08REVO7549383472',
 * hardcoded Account '1023', and hardcoded Administration 'PeterPrive' as fallbacks
 * instead of requiring bankLookup and erroring when it's missing.
 *
 * Validates: Requirements 1.6, 1.7, 1.8, 2.6, 2.7, 2.8
 */
import fc from 'fast-check';
import { processRevolutTransaction } from '../components/BankingProcessor';

// Dutch header matching the Revolut CSV export format
const DUTCH_HEADER = [
  'Type', 'Product', 'Startdatum', 'Datum voltooid',
  'Beschrijving', 'Bedrag', 'Kosten', 'Valuta', 'Status', 'Saldo',
];

// Valid Revolut columns for a completed transaction
const validColumns = [
  'Kaartbetaling',          // 0  Type
  'Betaalrekening',         // 1  Product
  '2026-04-16 12:07:04',   // 2  Startdatum
  '2026-04-16 14:00:00',   // 3  Datum voltooid (must be non-empty)
  'Test Purchase',          // 4  Beschrijving
  '-29.06',                 // 5  Bedrag (non-zero)
  '0.00',                   // 6  Kosten
  'EUR',                    // 7  Valuta
  'VOLTOOID',               // 8  Status
  '1200.50',                // 9  Saldo (must be non-empty)
];

describe('Bug Condition Exploration — Bank Account Lookup Hardcoded Fallbacks', () => {
  // -----------------------------------------------------------------------
  // Test C: processRevolutTransaction with bankLookup = undefined
  // -----------------------------------------------------------------------

  describe('processRevolutTransaction with bankLookup = undefined', () => {
    it('should throw an error or return empty when bankLookup is undefined', () => {
      /**
       * **Validates: Requirements 1.8, 2.7, 2.8**
       *
       * On UNFIXED code: returns transactions with hardcoded Account='1023',
       * Administration='PeterPrive', Ref1='NL08REVO7549383472'.
       * Expected: should throw an error OR return empty array when bankLookup
       * is undefined (bank account not configured).
       *
       * Test FAILS on unfixed code because it silently uses hardcoded fallbacks.
       */
      let threw = false;
      let result: any[] = [];

      try {
        result = processRevolutTransaction(validColumns, 0, undefined, 'test.tsv', DUTCH_HEADER);
      } catch {
        threw = true;
      }

      // Either it threw (correct) or it returned empty (acceptable)
      // On UNFIXED code: it returns transactions with hardcoded values → FAILS
      const isCorrectBehavior = threw || result.length === 0;
      expect(isCorrectBehavior).toBe(true);
    });

    it('should NOT use hardcoded Account 1023 when bankLookup is undefined', () => {
      /**
       * **Validates: Requirements 1.8, 2.8**
       *
       * On UNFIXED code: uses '1023' as fallback Account code.
       */
      let result: any[] = [];
      try {
        result = processRevolutTransaction(validColumns, 0, undefined, 'test.tsv', DUTCH_HEADER);
      } catch {
        // Throwing is correct behavior — test passes
        return;
      }

      // If it didn't throw, check no hardcoded values are used
      for (const tx of result) {
        expect(tx.Debet).not.toBe('1023');
        expect(tx.Credit).not.toBe('1023');
      }
    });

    it('should NOT use hardcoded Administration PeterPrive when bankLookup is undefined', () => {
      /**
       * **Validates: Requirements 1.8, 2.8**
       *
       * On UNFIXED code: uses 'PeterPrive' as fallback Administration.
       */
      let result: any[] = [];
      try {
        result = processRevolutTransaction(validColumns, 0, undefined, 'test.tsv', DUTCH_HEADER);
      } catch {
        return;
      }

      for (const tx of result) {
        expect(tx.Administration).not.toBe('PeterPrive');
      }
    });
  });

  // -----------------------------------------------------------------------
  // Test D: processRevolutTransaction with valid bankLookup — Ref1 should
  //         use bankLookup.rekeningNummer, not hardcoded IBAN
  // -----------------------------------------------------------------------

  describe('processRevolutTransaction with valid bankLookup', () => {
    it('should use bankLookup.rekeningNummer for Ref1, not hardcoded IBAN', () => {
      /**
       * **Validates: Requirements 1.6, 2.6, 3.6**
       *
       * On UNFIXED code: Ref1 is always 'NL08REVO7549383472' (hardcoded revolutIban)
       * regardless of what bankLookup.rekeningNummer contains.
       * Expected: Ref1 should be bankLookup.rekeningNummer.
       */
      const bankLookup = {
        Account: '1050',
        administration: 'CustomTenant',
        rekeningNummer: 'NL05REVO8814090866',
      };

      const result = processRevolutTransaction(validColumns, 0, bankLookup, 'test.tsv', DUTCH_HEADER);

      expect(result.length).toBeGreaterThan(0);

      for (const tx of result) {
        // On UNFIXED code: Ref1 is 'NL08REVO7549383472' → FAILS
        expect(tx.Ref1).toBe('NL05REVO8814090866');
      }
    });

    it('should use bankLookup.Account for Debet/Credit, not hardcoded 1023', () => {
      /**
       * **Validates: Requirements 1.8, 2.8**
       *
       * Verify that when bankLookup IS provided, the function uses
       * bankLookup.Account values (not hardcoded '1023').
       * On UNFIXED code: this actually works because of the || fallback,
       * but Ref1 is still hardcoded. This test should pass on unfixed code.
       */
      const bankLookup = {
        Account: '1050',
        administration: 'CustomTenant',
        rekeningNummer: 'NL05REVO8814090866',
      };

      const result = processRevolutTransaction(validColumns, 0, bankLookup, 'test.tsv', DUTCH_HEADER);

      expect(result.length).toBeGreaterThan(0);

      // The main transaction has negative amount → Credit should be '1050'
      const mainTx = result[0];
      expect(mainTx.Credit).toBe('1050');
      expect(mainTx.Administration).toBe('CustomTenant');
    });
  });

  // -----------------------------------------------------------------------
  // Test E: processFiles IBAN validation uses hardcoded Revolut IBAN
  // -----------------------------------------------------------------------

  describe('processFiles hardcoded Revolut IBAN', () => {
    it('should document that processFiles hardcodes NL08REVO7549383472 for Revolut', () => {
      /**
       * **Validates: Requirements 1.6, 2.6**
       *
       * processFiles() in BankingProcessor.tsx hardcodes:
       *   iban = 'NL08REVO7549383472'
       * for Revolut file detection and passes:
       *   lookupData.bank_accounts.find(ba => ba.rekeningNummer === 'NL08REVO7549383472')
       * to processRevolutTransaction.
       *
       * This is inside a React component hook (processFiles), so we cannot
       * directly import and test it. We verify the bug through
       * processRevolutTransaction's behavior instead.
       *
       * The hardcoded IBAN means:
       * - Tenants with different Revolut IBANs (e.g. NL05REVO8814090866) get wrong Ref1
       * - The bankLookup.find() may return undefined if the tenant's Revolut IBAN differs
       *
       * This test verifies that processRevolutTransaction with a different
       * tenant's Revolut IBAN still uses the hardcoded value (confirming the bug).
       */
      const bankLookup = {
        Account: '1050',
        administration: 'AnotherTenant',
        rekeningNummer: 'NL22REVO9999999999',
      };

      const result = processRevolutTransaction(validColumns, 0, bankLookup, 'revolut-statement.tsv', DUTCH_HEADER);

      expect(result.length).toBeGreaterThan(0);

      // On UNFIXED code: Ref1 is 'NL08REVO7549383472' (hardcoded), not the
      // tenant's actual Revolut IBAN → FAILS
      for (const tx of result) {
        expect(tx.Ref1).not.toBe('NL08REVO7549383472');
        expect(tx.Ref1).toBe('NL22REVO9999999999');
      }
    });
  });

  // -----------------------------------------------------------------------
  // Property-based test: Ref1 should always equal bankLookup.rekeningNummer
  // -----------------------------------------------------------------------

  describe('Property: Ref1 always equals bankLookup.rekeningNummer', () => {
    it('PROPERTY: for all valid bankLookup objects, Ref1 should use bankLookup.rekeningNummer', () => {
      /**
       * **Validates: Requirements 1.6, 2.6, 3.6**
       *
       * Generate random bank lookup objects with random Account codes,
       * administration names, and IBANs containing 'REVO'.
       * For each, call processRevolutTransaction with the bankLookup.
       * Assert Ref1 equals bankLookup.rekeningNummer (not hardcoded IBAN).
       *
       * On UNFIXED code: Ref1 is always 'NL08REVO7549383472' → FAILS
       */
      const bankLookupArb = fc.record({
        Account: fc.stringMatching(/^[1-9]\d{3}$/),
        administration: fc.string({ minLength: 3, maxLength: 20 }).filter(s => s.trim().length > 0),
        rekeningNummer: fc.stringMatching(/^NL\d{2}REVO\d{10}$/).filter(s => s !== 'NL08REVO7549383472'),
      });

      fc.assert(
        fc.property(bankLookupArb, (bankLookup) => {
          const result = processRevolutTransaction(
            validColumns, 0, bankLookup, 'test.tsv', DUTCH_HEADER
          );

          // Should produce transactions (valid completed row with non-zero amount)
          expect(result.length).toBeGreaterThan(0);

          for (const tx of result) {
            // On UNFIXED code: Ref1 is always 'NL08REVO7549383472' → FAILS
            expect(tx.Ref1).toBe(bankLookup.rekeningNummer);
          }
        }),
        { numRuns: 100 },
      );
    });
  });

  // -----------------------------------------------------------------------
  // Property-based test: undefined bankLookup should error, not use fallbacks
  // -----------------------------------------------------------------------

  describe('Property: undefined bankLookup should not produce hardcoded fallbacks', () => {
    it('PROPERTY: for all valid transaction rows, undefined bankLookup should throw or return empty', () => {
      /**
       * **Validates: Requirements 1.8, 2.7, 2.8**
       *
       * Generate random valid Revolut transaction rows.
       * Call processRevolutTransaction with bankLookup = undefined.
       * Assert it either throws or returns empty — never uses hardcoded values.
       *
       * On UNFIXED code: returns transactions with '1023'/'PeterPrive' → FAILS
       */
      const nonZeroAmount = fc.oneof(
        fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => `-${v.toFixed(2)}`),
        fc.double({ min: 0.01, max: 9999.99, noNaN: true }).map(v => v.toFixed(2)),
      );

      const description = fc.oneof(
        fc.constant('Albert Heijn'),
        fc.constant('Bol.com'),
        fc.string({ minLength: 1, maxLength: 30 }).filter(s => s.trim().length > 0),
      );

      const saldo = fc.double({ min: 0.01, max: 99999.99, noNaN: true }).map(v => v.toFixed(2));

      const rowArb = fc.tuple(description, nonZeroAmount, saldo).map(
        ([desc, amount, bal]) => [
          'Kaartbetaling',          // 0  Type
          'Betaalrekening',         // 1  Product
          '2026-04-16 12:07:04',   // 2  Startdatum
          '2026-04-16 14:00:00',   // 3  Datum voltooid
          desc,                     // 4  Beschrijving
          amount,                   // 5  Bedrag
          '0.00',                   // 6  Kosten
          'EUR',                    // 7  Valuta
          'VOLTOOID',               // 8  Status
          bal,                      // 9  Saldo
        ]
      );

      fc.assert(
        fc.property(rowArb, (columns: string[]) => {
          let threw = false;
          let result: any[] = [];

          try {
            result = processRevolutTransaction(columns, 0, undefined, 'test.tsv', DUTCH_HEADER);
          } catch {
            threw = true;
          }

          // Either threw (correct) or returned empty (acceptable)
          // On UNFIXED code: returns transactions with hardcoded values → FAILS
          const isCorrectBehavior = threw || result.length === 0;
          expect(isCorrectBehavior).toBe(true);
        }),
        { numRuns: 50 },
      );
    });
  });
});
