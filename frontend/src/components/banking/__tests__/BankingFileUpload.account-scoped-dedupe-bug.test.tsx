/**
 * Bug Condition Exploration Test — Account-Scoped Pre-Display Dedupe
 *
 * Property 1: Bug Condition — Per-Account Pre-Display Dedupe Keeps Cross-Account Rows
 *
 * CRITICAL: These tests encode the EXPECTED (correct) behavior.
 * On the UNFIXED `processFiles` they MUST FAIL — failure confirms the bug exists.
 * After the PRIMARY fix (Task 4) is applied, these same tests validate the fix.
 *
 * DO NOT fix the tests or the production code at this stage — a failing test here
 * is the SUCCESS outcome for this task.
 *
 * Bug condition C(input): a parsed import contains a row whose bank account (`Ref1`)
 * differs from the FIRST parsed row's `Ref1`, whose `Ref2` (Rabobank `Volgnr`)
 * collides with a DIFFERENT account's existing sequences under the same tenant, and
 * for which NO record exists for its own `(Ref1, Ref2)`.
 *
 * Expected behavior P: the row survives the per-account pre-display dedupe and reaches
 * `onTransactionsLoaded` (shown in the review grid).
 *
 * Root cause being surfaced (BankingFileUpload.tsx → processFiles):
 *   const iban = allTransactions[0]?.Ref1;                               // FIRST row only
 *   const sequences = allTransactions.map(t => t.Ref2).filter(Boolean);  // ALL rows
 *   // POST /api/banking/check-sequences { iban, sequences }
 *   const filteredTransactions = allTransactions.filter(
 *     t => !checkResult.duplicates.includes(t.Ref2));                    // Ref2-only filter
 *
 * **Validates: Requirements 2.1, 2.2, 2.3**
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
import type { LookupData, BankAccount } from '../../BankingProcessor.types';
import type { Transaction } from '../../BankingProcessor';
import { createMockResponse } from '../../../test-utils/mockHelpers';

// ---------------------------------------------------------------------------
// Fixture constants — the reported case (kimgeers)
// ---------------------------------------------------------------------------

const IBAN_NL98 = 'NL98RABO0174003390'; // account 1002 "Lopende rekening" (has existing rows)
const IBAN_NL60 = 'NL60RABO1101699949'; // account 1003 "Spaar rekening"   (0 existing rows)
const ACCOUNT_NL98 = '1002';
const ACCOUNT_NL60 = '1003';
const TENANT = 'TestTenant';

function knownAccounts(): BankAccount[] {
  return [
    { rekeningNummer: IBAN_NL98, Account: ACCOUNT_NL98, administration: TENANT },
    { rekeningNummer: IBAN_NL60, Account: ACCOUNT_NL60, administration: TENANT },
  ];
}

function buildLookupData(bankAccounts: BankAccount[]): LookupData {
  return {
    accounts: [],
    descriptions: [],
    bank_accounts: bankAccounts,
    credit_card_accounts: [],
    exchange_rate_account: null,
  };
}

// ---------------------------------------------------------------------------
// Rabobank CSV builder
// ---------------------------------------------------------------------------

/**
 * Build a single Rabobank CSV data row (22-column layout) for the given IBAN and
 * Volgnr. processRabobankTransaction reads: col 0 = IBAN (Ref1), col 3 = Volgnr
 * (Ref2 after parseInt), col 4 = date, col 6 = amount, col 7 = saldo.
 */
function rabobankRow(iban: string, volgnr: number, amount = '-29.06'): string {
  const cols = new Array(22).fill('');
  cols[0] = iban;
  cols[3] = volgnr.toString().padStart(18, '0'); // zero-padded Volgnr like the real CSV
  cols[4] = '2026-04-16';
  cols[6] = amount;
  cols[7] = '1250.00';
  cols[9] = 'Albert Heijn';
  return cols.join(',');
}

/**
 * Build a single-file Rabobank CSV containing rows for one or more accounts, in the
 * order given. The first data row's IBAN is what the unfixed processFiles uses for
 * the whole-file duplicate check.
 */
function rabobankFile(rows: Array<{ iban: string; volgnr: number }>, name = 'CSV_O_accounts_2026.csv'): File {
  const header = new Array(22).fill('').map((_, i) => `col${i}`).join(',');
  const body = rows.map(r => rabobankRow(r.iban, r.volgnr)).join('\n');
  return new File([`${header}\n${body}`], name, { type: 'text/csv' });
}

// ---------------------------------------------------------------------------
// Per-account check-sequences mock
// ---------------------------------------------------------------------------

/**
 * Install a check-sequences mock that answers PER IBAN from the request body:
 * for each `iban`, `existingByIban[iban]` is the set of Volgnr that already exist in
 * mutaties for that account; the endpoint returns the intersection with the requested
 * `sequences` (exactly like the real backend scoped to that one IBAN).
 *
 * This correctly models the backend: the UNFIXED frontend only ever calls it ONCE,
 * with the first row's IBAN; the FIXED frontend will call it once per distinct IBAN.
 */
function installCheckSequencesMock(existingByIban: Record<string, number[]>) {
  mockAuthenticatedPost.mockImplementation(async (url: string, body: any) => {
    if (typeof url === 'string' && url.includes('/api/banking/check-sequences')) {
      const iban: string = body?.iban;
      const sequences: string[] = body?.sequences ?? [];
      const existing = new Set((existingByIban[iban] ?? []).map(n => n.toString()));
      const duplicates = sequences.filter(s => existing.has(s));
      return createMockResponse({ body: { success: true, duplicates } });
    }
    return createMockResponse({ body: { success: true, duplicates: [] } });
  });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('Bug Condition Exploration — Account-Scoped Pre-Display Dedupe', () => {
  const onTransactionsLoaded = vi.fn();
  const setLoading = vi.fn();
  const setMessage = vi.fn();
  const setLookupData = vi.fn();
  const mapLookupData = vi.fn((data: any) => data);

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

  /** The rows passed to onTransactionsLoaded on its last (and only) invocation. */
  function loadedRows(): Transaction[] {
    const lastCall = onTransactionsLoaded.mock.calls[onTransactionsLoaded.mock.calls.length - 1];
    return (lastCall?.[0] as Transaction[]) ?? [];
  }

  /** Rows passed to onTransactionsLoaded whose Ref1 equals the given IBAN. */
  function loadedRowsForIban(iban: string): Transaction[] {
    return loadedRows().filter(t => t.Ref1 === iban);
  }

  /** How many distinct IBANs were sent to /api/banking/check-sequences. */
  function checkSequencesIbansCalled(): string[] {
    return mockAuthenticatedPost.mock.calls
      .filter(([url]) => typeof url === 'string' && url.includes('/api/banking/check-sequences'))
      .map(([, body]) => body?.iban as string);
  }

  function resetMocks() {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue(TENANT);
    // Default: no duplicates for any account (overridden per test).
    installCheckSequencesMock({});
  }

  beforeEach(() => {
    resetMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // Test case 1 — Cross-account drop
  // =========================================================================
  // NL98 (first account) already has Volgnr 1..5 in mutaties; NL60 (second account)
  // brings genuinely new rows Volgnr 1..5. Under the unfixed single-IBAN check, the
  // whole file is checked against NL98's existing 1..5, and the Ref2-only filter
  // drops every NL60 row — 0 of the 5 reach onTransactionsLoaded.
  // =========================================================================

  it('TC1: all 5 new NL60 rows reach onTransactionsLoaded even though NL98 already has Volgnr 1..5', async () => {
    installCheckSequencesMock({
      [IBAN_NL98]: [1, 2, 3, 4, 5], // NL98 existing sequences
      [IBAN_NL60]: [],              // NL60 has nothing yet
    });

    // First row is NL98 (so the unfixed check keys on NL98), followed by 5 new NL60 rows.
    const file = rabobankFile([
      { iban: IBAN_NL98, volgnr: 10 }, // a fresh NL98 row so NL98 has at least one surviving row
      { iban: IBAN_NL60, volgnr: 1 },
      { iban: IBAN_NL60, volgnr: 2 },
      { iban: IBAN_NL60, volgnr: 3 },
      { iban: IBAN_NL60, volgnr: 4 },
      { iban: IBAN_NL60, volgnr: 5 },
    ]);

    renderComponent(buildLookupData(knownAccounts()));
    await selectAndProcess([file]);

    expect(onTransactionsLoaded).toHaveBeenCalled();

    // EXPECTED (correct) BEHAVIOR — all 5 NL60 rows survive the per-account dedupe.
    // On UNFIXED code this FAILS: 0 NL60 rows reach onTransactionsLoaded.
    const nl60 = loadedRowsForIban(IBAN_NL60);
    expect(nl60.map(t => t.Ref2).sort()).toEqual(['1', '2', '3', '4', '5']);
    expect(nl60).toHaveLength(5);
  });

  // =========================================================================
  // Test case 2 — Single second-account row
  // =========================================================================
  // NL98 existing Volgnr = 1; one new NL60 row with Volgnr = 1. The single NL60 row
  // is genuinely new for its own account but is dropped as a duplicate of NL98's 1.
  // =========================================================================

  it('TC2: a single new NL60 row (Volgnr 1) survives even though NL98 already has Volgnr 1', async () => {
    installCheckSequencesMock({
      [IBAN_NL98]: [1],
      [IBAN_NL60]: [],
    });

    const file = rabobankFile([
      { iban: IBAN_NL98, volgnr: 2 }, // fresh NL98 row keeps NL98 as the first-row IBAN
      { iban: IBAN_NL60, volgnr: 1 },
    ]);

    renderComponent(buildLookupData(knownAccounts()));
    await selectAndProcess([file]);

    expect(onTransactionsLoaded).toHaveBeenCalled();

    // EXPECTED: the one NL60 row reaches the grid. UNFIXED: filtered out as duplicate.
    const nl60 = loadedRowsForIban(IBAN_NL60);
    expect(nl60).toHaveLength(1);
    expect(nl60[0].Ref2).toBe('1');
  });

  // =========================================================================
  // Test case 3 — Out-of-order first row (edge case)
  // =========================================================================
  // The FIRST parsed row belongs to NL60; later rows belong to NL98. NL98 is the
  // account whose Volgnr collides but it is NOT first. The unfixed single-IBAN check
  // keys on NL60, so NL98's genuinely new rows (whose Volgnr collide with NL60's
  // existing set here) are dropped. This characterizes the allTransactions[0]?.Ref1
  // single-IBAN assumption regardless of ordering.
  // =========================================================================

  it('TC3: with NL60 first, both accounts\' genuinely new rows reach onTransactionsLoaded', async () => {
    // NL60 is the first-row account; it already has Volgnr 1..3 in mutaties.
    // NL98 brings genuinely new rows with Volgnr 1..3 (collide with NL60's existing).
    installCheckSequencesMock({
      [IBAN_NL60]: [1, 2, 3],
      [IBAN_NL98]: [],
    });

    const file = rabobankFile([
      { iban: IBAN_NL60, volgnr: 10 }, // first row → unfixed check keys on NL60
      { iban: IBAN_NL98, volgnr: 1 },
      { iban: IBAN_NL98, volgnr: 2 },
      { iban: IBAN_NL98, volgnr: 3 },
    ]);

    renderComponent(buildLookupData(knownAccounts()));
    await selectAndProcess([file]);

    expect(onTransactionsLoaded).toHaveBeenCalled();

    // EXPECTED: NL98's 3 new rows survive (they are new for NL98). On UNFIXED code
    // they are dropped because the file-wide check keys on NL60's existing 1..3.
    const nl98 = loadedRowsForIban(IBAN_NL98);
    expect(nl98.map(t => t.Ref2).sort()).toEqual(['1', '2', '3']);
    // And NL60's genuinely new first row (Volgnr 10) also survives.
    const nl60 = loadedRowsForIban(IBAN_NL60);
    expect(nl60.map(t => t.Ref2)).toEqual(['10']);
  });

  // =========================================================================
  // Test case 4 — One check-sequences call per distinct account
  // =========================================================================
  // The correct behavior calls check-sequences once per distinct Ref1. The unfixed
  // code makes exactly ONE call (for the first row's IBAN only).
  // =========================================================================

  it('TC4: check-sequences is called once per distinct account IBAN (NL98 and NL60)', async () => {
    installCheckSequencesMock({
      [IBAN_NL98]: [1, 2, 3, 4, 5],
      [IBAN_NL60]: [],
    });

    const file = rabobankFile([
      { iban: IBAN_NL98, volgnr: 10 },
      { iban: IBAN_NL60, volgnr: 1 },
      { iban: IBAN_NL60, volgnr: 2 },
    ]);

    renderComponent(buildLookupData(knownAccounts()));
    await selectAndProcess([file]);

    // EXPECTED: both IBANs queried. UNFIXED: only NL98 (the first row's IBAN) queried.
    const ibans = checkSequencesIbansCalled();
    expect(new Set(ibans)).toEqual(new Set([IBAN_NL98, IBAN_NL60]));
  });

  // =========================================================================
  // PROPERTY — scoped PBT: for all two-account parses where NL60 rows are genuinely
  // new (no existing NL60 sequence) but their Volgnr collide with NL98's existing
  // set, every NL60 row survives the per-account pre-display dedupe.
  // =========================================================================

  fcTest.prop(
    [
      fc.integer({ min: 1, max: 8 }), // how many new NL60 rows (Volgnr 1..n)
    ],
    { numRuns: 15 },
  )(
    'PROPERTY: for a two-account parse, every genuinely-new NL60 row survives even when its Volgnr collides with NL98 existing sequences',
    async (nNl60) => {
      const existingNl98 = Array.from({ length: 8 }, (_, i) => i + 1); // NL98 has 1..8
      installCheckSequencesMock({
        [IBAN_NL98]: existingNl98,
        [IBAN_NL60]: [], // NL60 genuinely empty
      });

      const nl60Rows = Array.from({ length: nNl60 }, (_, i) => ({ iban: IBAN_NL60, volgnr: i + 1 }));
      const file = rabobankFile([
        { iban: IBAN_NL98, volgnr: 100 }, // NL98 first-row anchor (new, survives)
        ...nl60Rows,
      ]);

      const { unmount } = renderComponent(buildLookupData(knownAccounts()));
      await selectAndProcess([file]);

      const nl60 = loadedRowsForIban(IBAN_NL60);
      const expected = nl60Rows.map(r => r.volgnr.toString()).sort();
      // EXPECTED: all nNl60 rows survive. UNFIXED: 0 survive (all collide with NL98).
      expect(nl60.map(t => t.Ref2).sort()).toEqual(expected);

      unmount();
      resetMocks();
    },
  );
});
