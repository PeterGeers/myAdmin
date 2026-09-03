/**
 * Preservation Property Tests — Account Resolution (BEFORE fix)
 *
 * Property 2: Preservation — Single candidate auto-select, zero candidate error,
 * credit card unchanged, processRevolutTransaction determinism.
 *
 * These tests MUST PASS on unfixed code — they capture existing correct behavior
 * that must be preserved after the multi-account disambiguation fix is applied.
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { test as fcTest } from '@fast-check/vitest';
import fc from 'fast-check';

// ---------------------------------------------------------------------------
// Mocks — must be declared before importing the component
// ---------------------------------------------------------------------------

const mockAuthenticatedGet = vi.fn();
const mockAuthenticatedPost = vi.fn();

vi.mock('../../../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockAuthenticatedGet(...args),
  authenticatedPost: (...args: any[]) => mockAuthenticatedPost(...args),
}));

vi.mock('../../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'TestTenant', tenants: ['TestTenant'] }),
}));

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: Record<string, any>) => {
      if (params) return `${key}:${JSON.stringify(params)}`;
      return key;
    },
    i18n: { language: 'en' },
  }),
}));

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = { selectedTenant: 'TestTenant' };
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Import component and utilities after mocks
import BankingFileUpload from '../../BankingFileUpload';
import type { LookupData, Transaction } from '../../BankingProcessor.types';
import { processRevolutTransaction } from '../../BankingProcessor.utils';
import { createMockResponse } from '../../../test-utils/mockHelpers';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a single Revolut bank account */
function arbitrarySingleRevolutAccount(): fc.Arbitrary<{ rekeningNummer: string; Account: string; administration: string }> {
  return fc.tuple(
    fc.integer({ min: 1000, max: 9999 }),
    fc.stringMatching(/^NL[0-9]{2}REVO[0-9]{10}$/)
  ).map(([acctNum, iban]) => ({
    rekeningNummer: iban,
    Account: acctNum.toString(),
    administration: 'TestTenant',
  }));
}

/** Generate non-Revolut bank accounts (Rabobank-style) that don't contain 'REVO' */
function arbitraryNonRevolutAccount(): fc.Arbitrary<{ rekeningNummer: string; Account: string; administration: string }> {
  return fc.tuple(
    fc.integer({ min: 1000, max: 9999 }),
    fc.stringMatching(/^NL[0-9]{2}RABO[0-9]{10}$/)
  ).map(([acctNum, iban]) => ({
    rekeningNummer: iban,
    Account: acctNum.toString(),
    administration: 'TestTenant',
  }));
}

/** Generate 0-3 non-Revolut accounts (to ensure no REVO match exists) */
function arbitraryOnlyNonRevolutAccounts(): fc.Arbitrary<Array<{ rekeningNummer: string; Account: string; administration: string }>> {
  return fc.array(arbitraryNonRevolutAccount(), { minLength: 1, maxLength: 3 });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Create a minimal Revolut CSV file content (Dutch format).
 */
function createRevolutFileContent(): string {
  const header = 'Type,Product,Startdatum,Datum voltooid,Beschrijving,Bedrag,Kosten,Valuta,Status,Saldo';
  const row = 'Kaartbetaling,Betaalrekening,2026-04-16 12:07:04,2026-04-16 13:00:00,Albert Heijn,-29.06,0.00,EUR,VOLTOOID,1250.00';
  return `${header}\n${row}`;
}

/**
 * Create a File object simulating a Revolut file upload.
 */
function createRevolutFile(content: string): File {
  return new File([content], 'account-statement_2026-01-01.csv', {
    type: 'text/csv',
  });
}

/**
 * Create a credit card CSV file with valid columns (13 columns minimum).
 */
function createCreditCardFileContent(iban: string): string {
  const header = 'IBAN,Munt,BIC,Volmachtnummer,Kaartnummer,Volgnr,Transactiedatum,Boekdatum,Bedrag,Omschrijving,Origineel bedrag,Originele munt,Koers';
  const row = `${iban},EUR,RABONL2U,NL99RABO9999999999,1234567890,001,2026-04-16,2026-04-16,-25.50,Restaurant Dinner,,,`;
  return `${header}\n${row}`;
}

function createCreditCardFile(content: string): File {
  return new File([content], 'CSV_CC_test.csv', {
    type: 'text/csv',
  });
}

function buildLookupData(
  bankAccounts: Array<{ rekeningNummer: string; Account: string; administration: string }>,
  creditCardAccounts: Array<{ iban: string; Account: string; card_number: string; administration: string }> = [],
  exchangeRateAccount: string | null = null,
): LookupData {
  return {
    accounts: [],
    descriptions: [],
    bank_accounts: bankAccounts,
    credit_card_accounts: creditCardAccounts,
    exchange_rate_account: exchangeRateAccount,
  };
}

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

describe('Preservation Property Tests — Account Resolution', () => {
  const defaultOnTransactionsLoaded = vi.fn();
  const defaultSetLoading = vi.fn();
  const defaultSetMessage = vi.fn();
  const defaultSetLookupData = vi.fn();
  const defaultMapLookupData = vi.fn((data: any) => data);

  function renderComponent(lookupData: LookupData) {
    return render(
      <BankingFileUpload
        lookupData={lookupData}
        setLookupData={defaultSetLookupData}
        testMode={false}
        onTransactionsLoaded={defaultOnTransactionsLoaded}
        setLoading={defaultSetLoading}
        loading={false}
        message=""
        setMessage={defaultSetMessage}
        mapLookupData={defaultMapLookupData}
      />
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('TestTenant');

    // Default: no duplicates
    mockAuthenticatedPost.mockResolvedValue(
      createMockResponse({ body: { success: true, duplicates: [] } })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Test 1: Single Revolut account → auto-selects without dialog
  // Validates: Requirement 3.1
  // -------------------------------------------------------------------------

  describe('Single Revolut account — auto-select without dialog', () => {
    it('should process without dialog when exactly 1 Revolut account is configured', async () => {
      const accounts = [
        { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' },
        { rekeningNummer: 'NL44RABO0123456789', Account: '1100', administration: 'TestTenant' },
      ];
      const lookupData = buildLookupData(accounts);
      renderComponent(lookupData);

      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(inputEl).not.toBeNull();

      const file = createRevolutFile(createRevolutFileContent());

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      const processButton = await screen.findByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // PRESERVATION: No dialog shown for single account
      const dialog = screen.queryByRole('dialog');
      expect(dialog).toBeNull();

      // PRESERVATION: Transactions were loaded (processing completed)
      expect(defaultOnTransactionsLoaded).toHaveBeenCalled();

      // Verify the correct account was used (Ref1 = the REVO IBAN)
      const loadedTransactions = defaultOnTransactionsLoaded.mock.calls[0][0] as Transaction[];
      expect(loadedTransactions.length).toBeGreaterThan(0);
      expect(loadedTransactions[0].Ref1).toBe('NL08REVO7549383472');
    });

    fcTest.prop(
      [arbitrarySingleRevolutAccount()],
      { numRuns: 15 },
    )(
      'PROPERTY: for any single Revolut account, processing completes without dialog',
      async (revolutAccount) => {
        // Include the single Revolut account + a non-REVO account
        const accounts = [
          revolutAccount,
          { rekeningNummer: 'NL44RABO0123456789', Account: '9999', administration: 'TestTenant' },
        ];
        const lookupData = buildLookupData(accounts);
        const { unmount } = renderComponent(lookupData);

        const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
        if (!inputEl) {
          expect(inputEl).not.toBeNull();
          return;
        }

        const file = createRevolutFile(createRevolutFileContent());

        await act(async () => {
          fireEvent.change(inputEl, { target: { files: [file] } });
        });

        const processButton = screen.getByText('fileProcessing.processFiles');
        await act(async () => {
          fireEvent.click(processButton);
        });

        await waitFor(() => {
          expect(defaultSetLoading).toHaveBeenCalledWith(false);
        });

        // PRESERVATION: No dialog shown
        const dialog = screen.queryByRole('dialog');
        expect(dialog).toBeNull();

        // PRESERVATION: Processing completed
        expect(defaultOnTransactionsLoaded).toHaveBeenCalled();

        // Verify the correct account IBAN is in Ref1
        const loadedTransactions = defaultOnTransactionsLoaded.mock.calls[0][0] as Transaction[];
        if (loadedTransactions.length > 0) {
          expect(loadedTransactions[0].Ref1).toBe(revolutAccount.rekeningNummer);
        }

        unmount();
        vi.clearAllMocks();
        localStorageMock.getItem.mockReturnValue('TestTenant');
        mockAuthenticatedPost.mockResolvedValue(
          createMockResponse({ body: { success: true, duplicates: [] } })
        );
      },
    );
  });

  // -------------------------------------------------------------------------
  // Test 2: Zero Revolut accounts → error message, no processing
  // Validates: Requirement 3.1 (zero case preservation)
  // -------------------------------------------------------------------------

  describe('Zero Revolut accounts — error message and abort', () => {
    it('should show error when no Revolut account is configured', async () => {
      const accounts = [
        { rekeningNummer: 'NL44RABO0123456789', Account: '1100', administration: 'TestTenant' },
        { rekeningNummer: 'NL55INGB9876543210', Account: '1200', administration: 'TestTenant' },
      ];
      const lookupData = buildLookupData(accounts);
      renderComponent(lookupData);

      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(inputEl).not.toBeNull();

      const file = createRevolutFile(createRevolutFileContent());

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      const processButton = await screen.findByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // PRESERVATION: No dialog shown
      const dialog = screen.queryByRole('dialog');
      expect(dialog).toBeNull();

      // PRESERVATION: Error message shown about no configured account
      // After i18n refactoring, the message uses a translation key
      expect(defaultSetMessage).toHaveBeenCalledWith(
        expect.stringContaining('accountSelection.noAccountConfigured')
      );

      // PRESERVATION: Transactions NOT loaded (processing aborted)
      expect(defaultOnTransactionsLoaded).not.toHaveBeenCalled();
    });

    fcTest.prop(
      [arbitraryOnlyNonRevolutAccounts()],
      { numRuns: 15 },
    )(
      'PROPERTY: for any set of non-Revolut accounts, Revolut file upload shows error',
      async (nonRevolutAccounts) => {
        const lookupData = buildLookupData(nonRevolutAccounts);
        const { unmount } = renderComponent(lookupData);

        const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
        if (!inputEl) {
          expect(inputEl).not.toBeNull();
          return;
        }

        const file = createRevolutFile(createRevolutFileContent());

        await act(async () => {
          fireEvent.change(inputEl, { target: { files: [file] } });
        });

        const processButton = screen.getByText('fileProcessing.processFiles');
        await act(async () => {
          fireEvent.click(processButton);
        });

        await waitFor(() => {
          expect(defaultSetLoading).toHaveBeenCalledWith(false);
        });

        // PRESERVATION: No dialog
        const dialog = screen.queryByRole('dialog');
        expect(dialog).toBeNull();

        // PRESERVATION: Error message about no Revolut account
        // After i18n refactoring, the message uses a translation key
        expect(defaultSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('accountSelection.noAccountConfigured')
        );

        // PRESERVATION: No transactions loaded
        expect(defaultOnTransactionsLoaded).not.toHaveBeenCalled();

        unmount();
        vi.clearAllMocks();
        localStorageMock.getItem.mockReturnValue('TestTenant');
        mockAuthenticatedPost.mockResolvedValue(
          createMockResponse({ body: { success: true, duplicates: [] } })
        );
      },
    );
  });

  // -------------------------------------------------------------------------
  // Test 3: Credit card file → uses credit_card_accounts lookup
  // Validates: Requirement 3.2
  // -------------------------------------------------------------------------

  describe('Credit card file — uses credit_card_accounts lookup', () => {
    it('should use credit_card_accounts lookup for CSV_CC_ prefixed files', async () => {
      const ccIban = 'NL99RABO9999999999';
      const bankAccounts = [
        { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' },
        { rekeningNummer: 'NL44REVO9988776655', Account: '1022', administration: 'TestTenant' },
      ];
      const creditCardAccounts = [
        { iban: ccIban, Account: '2100', card_number: '1234567890', administration: 'TestTenant' },
      ];
      const lookupData = buildLookupData(bankAccounts, creditCardAccounts);
      renderComponent(lookupData);

      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(inputEl).not.toBeNull();

      const file = createCreditCardFile(createCreditCardFileContent(ccIban));

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      const processButton = await screen.findByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // PRESERVATION: No dialog shown (credit card path doesn't trigger account resolution)
      const dialog = screen.queryByRole('dialog');
      expect(dialog).toBeNull();

      // PRESERVATION: Transactions loaded (processing completed via credit card path)
      expect(defaultOnTransactionsLoaded).toHaveBeenCalled();

      // Verify credit card account was used (Account from cc lookup)
      const loadedTransactions = defaultOnTransactionsLoaded.mock.calls[0][0] as Transaction[];
      expect(loadedTransactions.length).toBeGreaterThan(0);
      // Credit card transactions use cc Account for Credit field
      expect(loadedTransactions[0].Credit).toBe('2100');
    });
  });

  // -------------------------------------------------------------------------
  // Test 4: processRevolutTransaction determinism
  // Validates: Requirement 3.3
  // -------------------------------------------------------------------------

  describe('processRevolutTransaction determinism', () => {
    it('should produce identical output for the same inputs', () => {
      const bankLookup = { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' };
      const columns = ['Kaartbetaling', 'Betaalrekening', '2026-04-16 12:07:04', '2026-04-16 13:00:00', 'Albert Heijn', '-29.06', '0.00', 'EUR', 'VOLTOOID', '1250.00'];
      const header = ['Type', 'Product', 'Startdatum', 'Datum voltooid', 'Beschrijving', 'Bedrag', 'Kosten', 'Valuta', 'Status', 'Saldo'];
      const fileName = 'account-statement_2026-01-01.csv';

      const result1 = processRevolutTransaction(columns, 0, bankLookup, fileName, header);
      const result2 = processRevolutTransaction(columns, 0, bankLookup, fileName, header);

      // Identical structure
      expect(result1.length).toBe(result2.length);
      for (let i = 0; i < result1.length; i++) {
        expect(result1[i].Ref1).toBe(result2[i].Ref1);
        expect(result1[i].Debet).toBe(result2[i].Debet);
        expect(result1[i].Credit).toBe(result2[i].Credit);
        expect(result1[i].TransactionAmount).toBe(result2[i].TransactionAmount);
        expect(result1[i].TransactionDescription).toBe(result2[i].TransactionDescription);
        expect(result1[i].Administration).toBe(result2[i].Administration);
      }
    });

    fcTest.prop(
      [
        arbitrarySingleRevolutAccount(),
        fc.double({ min: -10000, max: 10000, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.string({ minLength: 1, maxLength: 50 }),
      ],
      { numRuns: 30 },
    )(
      'PROPERTY: processRevolutTransaction is deterministic for any valid input',
      (bankLookup, amount, fee, description) => {
        // Skip zero amounts (they produce empty arrays, not a bug)
        if (amount === 0 && fee === 0) return;

        const columns = [
          'Kaartbetaling',
          'Betaalrekening',
          '2026-04-16 12:07:04',
          '2026-04-16 13:00:00',
          description,
          amount.toFixed(2),
          fee.toFixed(2),
          'EUR',
          'VOLTOOID',
          '1250.00',
        ];
        const header = ['Type', 'Product', 'Startdatum', 'Datum voltooid', 'Beschrijving', 'Bedrag', 'Kosten', 'Valuta', 'Status', 'Saldo'];
        const fileName = 'account-statement_test.csv';

        const result1 = processRevolutTransaction(columns, 0, bankLookup, fileName, header);
        const result2 = processRevolutTransaction(columns, 0, bankLookup, fileName, header);

        expect(result1.length).toBe(result2.length);
        for (let i = 0; i < result1.length; i++) {
          expect(result1[i].Ref1).toBe(result2[i].Ref1);
          expect(result1[i].Ref1).toBe(bankLookup.rekeningNummer);
          expect(result1[i].Administration).toBe(bankLookup.administration);
          expect(result1[i].TransactionAmount).toBe(result2[i].TransactionAmount);
          expect(result1[i].Debet).toBe(result2[i].Debet);
          expect(result1[i].Credit).toBe(result2[i].Credit);
        }
      },
    );

    fcTest.prop(
      [
        arbitrarySingleRevolutAccount(),
      ],
      { numRuns: 20 },
    )(
      'PROPERTY: processRevolutTransaction always assigns bankLookup IBAN to Ref1',
      (bankLookup) => {
        const columns = [
          'Kaartbetaling',
          'Betaalrekening',
          '2026-04-16 12:07:04',
          '2026-04-16 13:00:00',
          'Test Description',
          '-50.00',
          '0.00',
          'EUR',
          'VOLTOOID',
          '1250.00',
        ];
        const header = ['Type', 'Product', 'Startdatum', 'Datum voltooid', 'Beschrijving', 'Bedrag', 'Kosten', 'Valuta', 'Status', 'Saldo'];
        const fileName = 'account-statement_test.csv';

        const results = processRevolutTransaction(columns, 0, bankLookup, fileName, header);

        // Every transaction MUST have the bankLookup IBAN in Ref1
        for (const txn of results) {
          expect(txn.Ref1).toBe(bankLookup.rekeningNummer);
        }
      },
    );
  });

  // -------------------------------------------------------------------------
  // Test 5: File type detection unchanged
  // Validates: Requirement 3.5
  // -------------------------------------------------------------------------

  describe('File type detection — unchanged', () => {
    it('should detect .tsv files as Revolut', async () => {
      const account = { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' };
      const lookupData = buildLookupData([account]);
      renderComponent(lookupData);

      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      // TSV file with tab-separated content
      const tsvContent = 'Type\tProduct\tStarted Date\tCompleted Date\tDescription\tAmount\tFee\tCurrency\tState\tBalance\n' +
        'CARD_PAYMENT\tCurrent\t2026-04-16 12:07:04\t2026-04-16 13:00:00\tAlbert Heijn\t-29.06\t0.00\tEUR\tCOMPLETED\t1250.00';
      const file = new File([tsvContent], 'revolut-statement.tsv', { type: 'text/tab-separated-values' });

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      const processButton = await screen.findByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // PRESERVATION: Processed without dialog, transactions loaded
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(defaultOnTransactionsLoaded).toHaveBeenCalled();

      const loadedTransactions = defaultOnTransactionsLoaded.mock.calls[0][0] as Transaction[];
      if (loadedTransactions.length > 0) {
        expect(loadedTransactions[0].Ref1).toBe('NL08REVO7549383472');
      }
    });

    it('should detect account-statement prefixed CSV files as Revolut', async () => {
      const account = { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' };
      const lookupData = buildLookupData([account]);
      renderComponent(lookupData);

      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = createRevolutFile(createRevolutFileContent());

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      const processButton = await screen.findByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // PRESERVATION: Processed correctly
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(defaultOnTransactionsLoaded).toHaveBeenCalled();
    });
  });
});
