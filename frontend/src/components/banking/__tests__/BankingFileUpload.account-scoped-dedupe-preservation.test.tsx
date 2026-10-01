/**
 * Preservation Property Tests — Account-Scoped Dedupe (frontend `processFiles`)
 *
 * Spec: banking-import-iban-account-resolution
 * Property 2: Preservation — Unchanged Behavior for Non-Colliding Inputs
 *
 * For any input where the bug condition does NOT hold (`isBugCondition` returns
 * false), the fixed `processFiles` must produce the SAME observable result as the
 * original (unfixed) code. The bug condition only involves a SECOND account whose
 * `Volgnr` collides with the FIRST account's existing sequences; everything below
 * stays on the non-colliding side of that line.
 *
 * METHODOLOGY: Observation-first. Every assertion encodes the behavior OBSERVED on
 * the UNFIXED `processFiles`, so these tests PASS now (locking in the baseline) and
 * must continue to pass after the per-account grouping fix (Task 4).
 *
 * Baseline behaviors captured (all with isBugCondition === false):
 *  - Single-account import preserved: a one-account Rabobank file makes exactly ONE
 *    `check-sequences` call and passes the surviving rows to onTransactionsLoaded
 *    (Req 3.1).
 *  - Same-account re-import still filtered: re-importing NL98 Ref2=1..47 (all in that
 *    account's returned duplicates) drops every row (Req 3.2).
 *  - Ref2 normalization preserved: processRabobankTransaction yields
 *    Ref2 = parseInt(columns[3] || '0').toString(); the dedupe compares on that
 *    normalized value (Req 3.3).
 *  - Resolution + popup preserved: per-row Debet/Credit resolution from
 *    lookupData.bank_accounts, and the account-selection popup, are unchanged
 *    (Req 3.4).
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
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

// `t` returns the raw key (with params appended) so we can assert on keys.
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: Record<string, any>) => {
      if (params) return `${key}:${JSON.stringify(params)}`;
      return key;
    },
    i18n: { language: 'en' },
  }),
}));

// Mock localStorage so the tenant guard passes.
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

// Import component after mocks
import BankingFileUpload from '../../BankingFileUpload';
import { processRabobankTransaction } from '../../BankingProcessor.utils';
import type { LookupData, BankAccount } from '../../BankingProcessor.types';
import { createMockResponse } from '../../../test-utils/mockHelpers';

// ---------------------------------------------------------------------------
// File builders — Rabobank CSV (22 columns; col 0 = IBAN, col 3 = Volgnr → Ref2)
// ---------------------------------------------------------------------------

const NL98 = 'NL98RABO0174003390';
const NL60 = 'NL60RABO1101699949';

/** Build one Rabobank CSV data row with the given IBAN, Volgnr and amount. */
function rabobankRow(iban: string, volgnr: number | string, amount = '-29.06'): string[] {
  const cols = new Array(22).fill('');
  cols[0] = iban;                 // IBAN → Ref1
  cols[3] = String(volgnr);       // Volgnr → Ref2
  cols[4] = '2026-04-16';         // date
  cols[6] = amount;               // amount
  cols[7] = '1250.00';            // saldo
  cols[9] = 'Albert Heijn';       // description
  return cols;
}

/** Build a Rabobank CSV File from a list of data rows. */
function rabobankFileFromRows(rows: string[][], name = 'CSV_O_2026.csv'): File {
  const header = new Array(22).fill('').map((_, i) => `col${i}`).join(',');
  const body = rows.map((r) => r.join(',')).join('\n');
  return new File([`${header}\n${body}`], name, { type: 'text/csv' });
}

/** Single-account file: `count` rows for one IBAN, Volgnr 1..count. */
function singleAccountFile(iban: string, count: number): File {
  const rows: string[][] = [];
  for (let v = 1; v <= count; v++) rows.push(rabobankRow(iban, v));
  return rabobankFileFromRows(rows);
}

// ---------------------------------------------------------------------------
// Test scaffolding
// ---------------------------------------------------------------------------

describe('Preservation — account-scoped dedupe leaves non-colliding inputs unchanged', () => {
  const onTransactionsLoaded = vi.fn();
  const setLoading = vi.fn();
  const setMessage = vi.fn();
  const setLookupData = vi.fn();
  const mapLookupData = vi.fn((data: any) => data);

  function buildLookupData(bankAccounts: BankAccount[]): LookupData {
    return {
      accounts: [],
      descriptions: [],
      bank_accounts: bankAccounts,
      credit_card_accounts: [],
      exchange_rate_account: null,
    };
  }

  function renderComponent(lookupData: LookupData) {
    return render(
      <BankingFileUpload
        lookupData={lookupData}
        setLookupData={setLookupData}
        testMode={false}
        onTransactionsLoaded={onTransactionsLoaded}
        setLoading={setLoading}
        loading={false}
        message=""
        setMessage={setMessage}
        mapLookupData={mapLookupData}
      />
    );
  }

  /** Select files, click Process, wait for processing to settle. */
  async function selectAndProcess(files: File[]) {
    const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(inputEl).not.toBeNull();

    await act(async () => {
      fireEvent.change(inputEl, { target: { files } });
    });

    const processButton = await screen.findByText('fileProcessing.processFiles');
    await act(async () => {
      fireEvent.click(processButton);
    });

    await waitFor(() => {
      expect(setLoading).toHaveBeenCalledWith(false);
    });
  }

  /** The Transaction[] passed to the LAST onTransactionsLoaded call (or null). */
  function lastLoadedTransactions(): any[] | null {
    const calls = onTransactionsLoaded.mock.calls;
    if (calls.length === 0) return null;
    return calls[calls.length - 1][0];
  }

  /** All check-sequences request bodies ({ iban, sequences, test_mode }). */
  function checkSequencesCalls(): Array<{ iban: string; sequences: string[]; test_mode: boolean }> {
    return mockAuthenticatedPost.mock.calls
      .filter(([url]) => url === '/api/banking/check-sequences')
      .map(([, body]) => body);
  }

  /**
   * Make `check-sequences` return per-IBAN duplicates. The mock keys off the
   * `iban` in the request body, so it behaves correctly for BOTH the unfixed code
   * (one call for the first row's IBAN) and the fixed code (one call per account).
   */
  function mockCheckSequencesByIban(existingByIban: Record<string, string[]>) {
    mockAuthenticatedPost.mockImplementation((url: string, body: any) => {
      if (url === '/api/banking/check-sequences') {
        const existing = existingByIban[body.iban] ?? [];
        const requested: string[] = body.sequences ?? [];
        const duplicates = requested.filter((seq) => existing.includes(seq));
        return Promise.resolve(
          createMockResponse({ body: { success: true, duplicates } })
        );
      }
      return Promise.resolve(createMockResponse({ body: { success: true } }));
    });
  }

  function resetMocks() {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('TestTenant');
    // Default: no duplicates for any account.
    mockCheckSequencesByIban({});
  }

  beforeEach(() => {
    resetMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // 3.1 — Single-account import preserved
  // =========================================================================

  it('3.1 single-account file with no existing duplicates → one check-sequences call, all rows loaded', async () => {
    const account: BankAccount = { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' };
    renderComponent(buildLookupData([account]));

    // No existing sequences for NL98 → nothing filtered.
    mockCheckSequencesByIban({ [NL98]: [] });

    await selectAndProcess([singleAccountFile(NL98, 5)]);

    // No popup (single resolved account), processing completed.
    expect(screen.queryByRole('dialog')).toBeNull();

    const loaded = lastLoadedTransactions();
    expect(loaded).not.toBeNull();
    expect(loaded!.length).toBe(5);
    // All loaded rows belong to the single account.
    expect(loaded!.every((t) => t.Ref1 === NL98)).toBe(true);
    expect(new Set(loaded!.map((t) => t.Ref2))).toEqual(new Set(['1', '2', '3', '4', '5']));

    // Exactly ONE check-sequences call for the single account, carrying only
    // that account's sequences and the request shape { iban, sequences, test_mode }.
    const calls = checkSequencesCalls();
    expect(calls.length).toBe(1);
    expect(calls[0].iban).toBe(NL98);
    expect(new Set(calls[0].sequences)).toEqual(new Set(['1', '2', '3', '4', '5']));
    expect(calls[0]).toHaveProperty('test_mode');
  });

  it('3.1 single-account file with partial existing duplicates → only new rows loaded', async () => {
    const account: BankAccount = { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' };
    renderComponent(buildLookupData([account]));

    // NL98 already has Ref2 1,2,3 → those are filtered, 4 and 5 survive.
    mockCheckSequencesByIban({ [NL98]: ['1', '2', '3'] });

    await selectAndProcess([singleAccountFile(NL98, 5)]);

    const loaded = lastLoadedTransactions();
    expect(loaded).not.toBeNull();
    expect(new Set(loaded!.map((t) => t.Ref2))).toEqual(new Set(['4', '5']));
    expect(loaded!.every((t) => t.Ref1 === NL98)).toBe(true);

    // Still exactly one call for the single account.
    expect(checkSequencesCalls().length).toBe(1);
  });

  // =========================================================================
  // 3.2 — Same-account re-import still filtered (every row a true duplicate)
  // =========================================================================

  it('3.2 re-importing the same account whose Ref2 are all existing duplicates → all rows filtered', async () => {
    const account: BankAccount = { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' };
    renderComponent(buildLookupData([account]));

    // All 47 rows already exist for NL98 (its OWN (Ref1, Ref2) triple exists).
    const existing = Array.from({ length: 47 }, (_, i) => String(i + 1));
    mockCheckSequencesByIban({ [NL98]: existing });

    await selectAndProcess([singleAccountFile(NL98, 47)]);

    const loaded = lastLoadedTransactions();
    expect(loaded).not.toBeNull();
    // Every row filtered as a (same-account) duplicate.
    expect(loaded!.length).toBe(0);
  });

  // =========================================================================
  // 3.3 — Ref2 normalization preserved (processRabobankTransaction)
  // =========================================================================

  it('3.3 processRabobankTransaction normalizes Ref2 via parseInt(columns[3] || "0").toString()', () => {
    const lookupData = buildLookupData([
      { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' },
    ]);

    // Zero-padded Volgnr → plain integer string.
    const padded = processRabobankTransaction(
      rabobankRow(NL98, '000000000000000007'), 0, lookupData, 'CSV_O.csv'
    );
    expect(padded).not.toBeNull();
    expect(padded!.Ref2).toBe('7');
    expect(padded!.Ref2).toBe(parseInt('000000000000000007' || '0').toString());

    // Plain integer Volgnr stays itself.
    const plain = processRabobankTransaction(
      rabobankRow(NL98, '42'), 1, lookupData, 'CSV_O.csv'
    );
    expect(plain!.Ref2).toBe('42');

    // Empty Volgnr normalizes to '0'.
    const empty = processRabobankTransaction(
      rabobankRow(NL98, ''), 2, lookupData, 'CSV_O.csv'
    );
    expect(empty!.Ref2).toBe('0');
  });

  // =========================================================================
  // 3.3 (grouping compares on normalized value) — a padded re-import of an
  // existing normalized Ref2 is still filtered, proving the dedupe compares on
  // the SAME normalized value.
  // =========================================================================

  it('3.3 dedupe compares on the normalized Ref2 (zero-padded re-import of existing "1" is filtered)', async () => {
    const account: BankAccount = { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' };
    renderComponent(buildLookupData([account]));

    // Existing stored sequence is the normalized "1".
    mockCheckSequencesByIban({ [NL98]: ['1'] });

    // Import a zero-padded Volgnr for the same account → normalizes to "1".
    await selectAndProcess([rabobankFileFromRows([rabobankRow(NL98, '000000000000000001')])]);

    // The single check-sequences call carries the NORMALIZED value "1".
    const calls = checkSequencesCalls();
    expect(calls.length).toBe(1);
    expect(calls[0].sequences).toEqual(['1']);

    // And the row is filtered as a duplicate (compared on the normalized value).
    const loaded = lastLoadedTransactions();
    expect(loaded).not.toBeNull();
    expect(loaded!.length).toBe(0);
  });

  // =========================================================================
  // 3.4 — Per-row account resolution (Debet/Credit) preserved
  // =========================================================================

  it('3.4 per-row Debet/Credit resolution from lookupData.bank_accounts is unchanged', () => {
    const lookupData = buildLookupData([
      { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' },
    ]);

    // Negative amount → bank account goes in Credit, Debet empty.
    const negative = processRabobankTransaction(
      rabobankRow(NL98, 1, '-29.06'), 0, lookupData, 'CSV_O.csv'
    );
    expect(negative!.Credit).toBe('1002');
    expect(negative!.Debet).toBe('');
    expect(negative!.Administration).toBe('TestTenant');

    // Positive amount → bank account goes in Debet, Credit empty.
    const positive = processRabobankTransaction(
      rabobankRow(NL98, 2, '+150.50'), 1, lookupData, 'CSV_O.csv'
    );
    expect(positive!.Debet).toBe('1002');
    expect(positive!.Credit).toBe('');
  });

  // =========================================================================
  // 3.4 — Account-selection popup preserved (ambiguous Revolut still opens it)
  //
  // This fix touches ONLY the Rabobank per-account dedupe; the popup mechanics
  // for an ambiguous resolution must be byte-for-byte unchanged.
  // =========================================================================

  it('3.4 ambiguous Revolut resolution still opens the account-selection popup', async () => {
    const revoA: BankAccount = { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' };
    const revoB: BankAccount = { rekeningNummer: 'NL00REVO0000000002', Account: '1201', administration: 'TestTenant' };
    renderComponent(buildLookupData([revoA, revoB]));

    const header = 'Type,Product,Startdatum,Datum voltooid,Beschrijving,Bedrag,Kosten,Valuta,Status,Saldo';
    const row = 'Kaartbetaling,Betaalrekening,2026-04-16 12:07:04,2026-04-16 13:00:00,Albert Heijn,-29.06,0.00,EUR,VOLTOOID,1250.00';
    const revolutFile = new File([`${header}\n${row}`], 'account-statement_2026.csv', { type: 'text/csv' });

    await selectAndProcess([revolutFile]);

    // Popup opens with the matching REVO candidates; processing paused.
    expect(screen.queryByRole('dialog')).not.toBeNull();
    expect(screen.queryByText(new RegExp(revoA.rekeningNummer))).not.toBeNull();
    expect(screen.queryByText(new RegExp(revoB.rekeningNummer))).not.toBeNull();
    expect(onTransactionsLoaded).not.toHaveBeenCalled();
  });

  // =========================================================================
  // PROPERTY (3.1 / 3.2): for all single-account imports with an arbitrary set
  // of already-existing sequences, exactly ONE check-sequences call is made and
  // the surviving rows are precisely those whose Ref2 is NOT already existing.
  // Single-account inputs never satisfy the bug condition.
  // =========================================================================

  fcTest.prop(
    [
      fc.integer({ min: 1, max: 12 }),          // number of rows in the file (Volgnr 1..n)
      fc.uniqueArray(fc.integer({ min: 1, max: 12 }), { maxLength: 12 }), // existing seqs
    ],
    { numRuns: 25 },
  )(
    'PROPERTY: single-account import makes one call and keeps exactly the non-existing rows',
    async (rowCount, existingNums) => {
      const account: BankAccount = { rekeningNummer: NL98, Account: '1002', administration: 'TestTenant' };
      const { unmount } = renderComponent(buildLookupData([account]));

      const existing = existingNums.map(String);
      mockCheckSequencesByIban({ [NL98]: existing });

      await selectAndProcess([singleAccountFile(NL98, rowCount)]);

      // Exactly one check-sequences call (single account).
      expect(checkSequencesCalls().length).toBe(1);

      const loaded = lastLoadedTransactions();
      expect(loaded).not.toBeNull();

      const allSeqs = Array.from({ length: rowCount }, (_, i) => String(i + 1));
      const expectedSurviving = allSeqs.filter((s) => !existing.includes(s));
      expect(new Set(loaded!.map((t) => t.Ref2))).toEqual(new Set(expectedSurviving));
      // Every surviving row belongs to the single account.
      expect(loaded!.every((t) => t.Ref1 === NL98)).toBe(true);

      unmount();
      resetMocks();
    },
  );
});
