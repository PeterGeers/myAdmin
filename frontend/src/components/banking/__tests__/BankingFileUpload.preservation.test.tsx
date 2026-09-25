/**
 * Preservation Property Tests — Non-`none` outcomes and popup mechanics unchanged
 *
 * Spec: revolut-iban-select-popup-fix
 * Property 2: Preservation — For any input where the bug condition does NOT hold
 * (`isBugCondition` returns false — resolution `resolved`, `ambiguous`, or a
 * credit-card file), the flow must behave exactly as it does today. The fix in a
 * later task only touches the `none` branch, so every other outcome and the popup
 * select/cancel mechanics must be untouched.
 *
 * METHODOLOGY: Observation-first. These assertions encode the observed baseline
 * behavior of the UNFIXED code so that they PASS now and continue to pass after the
 * fix, locking in the behavior to preserve.
 *
 * Baseline behaviors captured (all with isBugCondition === false):
 *  - `resolved` (single match): NO popup opens; files process directly with the
 *    auto-selected account (onTransactionsLoaded called, transactionsLoaded message,
 *    no noAccountConfigured error).
 *  - `ambiguous` (multiple matches): popup opens with EXACTLY the matching
 *    resolution.candidates (the REVO-matching subset — NOT the full known-accounts
 *    list); no error; processing paused (onTransactionsLoaded not yet called).
 *      - selecting a candidate resumes processing with the chosen account.
 *  - popup cancel: handleAccountSelectionCancel clears the dialog and the message;
 *    processing aborts (onTransactionsLoaded not called).
 *  - credit-card files (CSV_CC_* / RA_CC_*): route through the separate credit-card
 *    lookup/validation path; never enter the account-selection loop (no popup).
 *  - single-IBAN Rabobank file matching one configured account: resolves and
 *    processes with that account (no popup).
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
import type { LookupData, BankAccount, CreditCardAccount } from '../../BankingProcessor.types';
import { createMockResponse } from '../../../test-utils/mockHelpers';

// ---------------------------------------------------------------------------
// File builders
// ---------------------------------------------------------------------------

/** Minimal Revolut CSV content (Dutch header). Revolut files carry no IBAN. */
function revolutContent(): string {
  const header = 'Type,Product,Startdatum,Datum voltooid,Beschrijving,Bedrag,Kosten,Valuta,Status,Saldo';
  const row = 'Kaartbetaling,Betaalrekening,2026-04-16 12:07:04,2026-04-16 13:00:00,Albert Heijn,-29.06,0.00,EUR,VOLTOOID,1250.00';
  return `${header}\n${row}`;
}

/** A Revolut file — name starts with `account-statement`, matched by REVO. */
function revolutFile(name = 'account-statement_2026-08-01_2026-09-25_en-us_468cd1.csv'): File {
  return new File([revolutContent()], name, { type: 'text/csv' });
}

/**
 * Rabobank-style CSV with the full 22-column layout so processRabobankTransaction
 * (which requires columns.length >= 20) produces a transaction. Column 0 is the IBAN.
 */
function rabobankFile(iban: string, name = 'rabobank_2026.csv'): File {
  const cols = new Array(22).fill('');
  const header = cols.map((_, i) => `col${i}`).join(',');
  const row = [...cols];
  row[0] = iban;      // IBAN
  row[3] = '1';       // volgnummer → Ref2
  row[4] = '2026-04-16'; // date
  row[6] = '-29.06';  // amount
  row[7] = '1250.00'; // saldo
  row[9] = 'Albert Heijn';
  return new File([`${header}\n${row.join(',')}`], name, { type: 'text/csv' });
}

/** A credit-card file (CSV_CC_ prefix). Column 0 is the CC IBAN used for lookup. */
function creditCardFile(iban: string, name = 'CSV_CC_2026.csv'): File {
  const cols = new Array(13).fill('');
  const header = cols.map((_, i) => `col${i}`).join(',');
  const row = [...cols];
  row[0] = iban;       // CC IBAN → credit_card_accounts lookup
  row[6] = 'REF123';   // Ref2
  row[7] = '2026-04-16'; // date
  row[8] = '-29.06';   // amount
  row[9] = 'Albert Heijn'; // description
  return new File([`${header}\n${row.join(',')}`], name, { type: 'text/csv' });
}

// ---------------------------------------------------------------------------
// Test scaffolding
// ---------------------------------------------------------------------------

describe('Preservation — non-`none` outcomes and popup mechanics behave identically', () => {
  const onTransactionsLoaded = vi.fn();
  const setLoading = vi.fn();
  const setMessage = vi.fn();
  const setLookupData = vi.fn();
  const mapLookupData = vi.fn((data: any) => data);

  function buildLookupData(
    bankAccounts: BankAccount[],
    creditCardAccounts: CreditCardAccount[] = [],
  ): LookupData {
    return {
      accounts: [],
      descriptions: [],
      bank_accounts: bankAccounts,
      credit_card_accounts: creditCardAccounts,
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

  /** Select files, click Process, and wait for processing to settle. */
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

  /** Did the component show the no-account-configured error? */
  function noAccountErrorShown(): boolean {
    return setMessage.mock.calls.some(
      ([msg]) => typeof msg === 'string' && msg.includes('accountSelection.noAccountConfigured')
    );
  }

  /** Did the component show the "transactions loaded" success message? */
  function transactionsLoadedShown(): boolean {
    return setMessage.mock.calls.some(
      ([msg]) => typeof msg === 'string' && msg.includes('messages.transactionsLoaded')
    );
  }

  function resetMocks() {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('TestTenant');
    // Sequence check returns no duplicates (reached only if processing continues).
    mockAuthenticatedPost.mockResolvedValue(
      createMockResponse({ body: { success: true, duplicates: [] } })
    );
  }

  beforeEach(() => {
    resetMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // 3.1 — Resolved auto-select: single match, no popup, direct processing
  // =========================================================================

  it('3.1 resolved (single REVO match) → no popup, auto-selects and processes', async () => {
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' },
      { rekeningNummer: 'NL11RABO0111111111', Account: '1010', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts));

    await selectAndProcess([revolutFile()]);

    // No popup for a single, unambiguous match.
    expect(screen.queryByRole('dialog')).toBeNull();
    // Processing ran to completion (transactions loaded), no error.
    expect(onTransactionsLoaded).toHaveBeenCalled();
    expect(transactionsLoadedShown()).toBe(true);
    expect(noAccountErrorShown()).toBe(false);
  });

  // =========================================================================
  // 3.5 — Single-IBAN Rabobank file matching one configured account resolves
  // =========================================================================

  it('3.5 single-IBAN Rabobank file matching one account → no popup, resolves and processes', async () => {
    const iban = 'NL11RABO0111111111';
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: iban, Account: '1010', administration: 'TestTenant' },
      { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts));

    await selectAndProcess([rabobankFile(iban)]);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(onTransactionsLoaded).toHaveBeenCalled();
    expect(noAccountErrorShown()).toBe(false);
  });

  // =========================================================================
  // 3.2 — Ambiguous popup: opens with EXACTLY the matching candidates
  // =========================================================================

  it('3.2 ambiguous (multiple REVO matches) → popup opens with only the matching candidates', async () => {
    const revoA: BankAccount = { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' };
    const revoB: BankAccount = { rekeningNummer: 'NL00REVO0000000002', Account: '1201', administration: 'TestTenant' };
    const rabo: BankAccount = { rekeningNummer: 'NL11RABO0111111111', Account: '1010', administration: 'TestTenant' };
    renderComponent(buildLookupData([revoA, revoB, rabo]));

    await selectAndProcess([revolutFile()]);

    // Popup opens.
    expect(screen.queryByRole('dialog')).not.toBeNull();
    // Candidates are ONLY the REVO matches, not the full known-accounts list.
    expect(screen.queryByText(new RegExp(revoA.rekeningNummer))).not.toBeNull();
    expect(screen.queryByText(new RegExp(revoB.rekeningNummer))).not.toBeNull();
    // The non-matching Rabobank account must NOT be offered.
    expect(screen.queryByText(new RegExp(rabo.rekeningNummer))).toBeNull();
    // No error; processing paused (not yet completed).
    expect(noAccountErrorShown()).toBe(false);
    expect(onTransactionsLoaded).not.toHaveBeenCalled();
  });

  // =========================================================================
  // 3.3 (select) — selecting a candidate resumes processing with that account
  // =========================================================================

  it('3.3 selecting an account in the ambiguous popup resumes processing', async () => {
    const revoA: BankAccount = { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' };
    const revoB: BankAccount = { rekeningNummer: 'NL00REVO0000000002', Account: '1201', administration: 'TestTenant' };
    renderComponent(buildLookupData([revoA, revoB]));

    await selectAndProcess([revolutFile()]);
    expect(screen.queryByRole('dialog')).not.toBeNull();
    expect(onTransactionsLoaded).not.toHaveBeenCalled();

    // Pick the first candidate.
    const choice = screen.getByText(new RegExp(revoA.rekeningNummer));
    await act(async () => {
      fireEvent.click(choice);
    });

    await waitFor(() => {
      expect(onTransactionsLoaded).toHaveBeenCalled();
    });
    // Dialog dismissed after selection.
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(noAccountErrorShown()).toBe(false);
  });

  // =========================================================================
  // 3.3 (cancel) — cancelling the popup clears state and aborts processing
  // =========================================================================

  it('3.3 cancelling the ambiguous popup clears the dialog/message and aborts processing', async () => {
    const revoA: BankAccount = { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' };
    const revoB: BankAccount = { rekeningNummer: 'NL00REVO0000000002', Account: '1201', administration: 'TestTenant' };
    renderComponent(buildLookupData([revoA, revoB]));

    await selectAndProcess([revolutFile()]);
    expect(screen.queryByRole('dialog')).not.toBeNull();

    const cancelButton = screen.getByText('accountSelection.cancel');
    await act(async () => {
      fireEvent.click(cancelButton);
    });

    // Dialog closed, message cleared, processing never completed.
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    // handleAccountSelectionCancel calls setMessage('').
    expect(setMessage.mock.calls.some(([m]) => m === '')).toBe(true);
    expect(onTransactionsLoaded).not.toHaveBeenCalled();
  });

  // =========================================================================
  // 3.4 — Credit-card files never enter the account-selection loop (no popup)
  // =========================================================================

  it('3.4 credit-card file (CSV_CC_) routes through the CC path, never opens the selection popup', async () => {
    const ccIban = 'NL55CC000000000001';
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: 'NL00REVO0000000001', Account: '1200', administration: 'TestTenant' },
      { rekeningNummer: 'NL00REVO0000000002', Account: '1201', administration: 'TestTenant' },
    ];
    const creditCards: CreditCardAccount[] = [
      { iban: ccIban, Account: '1300', card_number: '1234', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts, creditCards));

    await selectAndProcess([creditCardFile(ccIban)]);

    // Even though there are multiple REVO accounts (which would be ambiguous for a
    // non-CC file), the CC file must not enter the selection loop → no popup.
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(noAccountErrorShown()).toBe(false);
    expect(onTransactionsLoaded).toHaveBeenCalled();
  });

  // =========================================================================
  // PROPERTY (3.1 / 3.2): across generated resolution scenarios, the observable
  // outcome (popup shown? which candidates? error? processing) matches the
  // recorded baseline.
  //
  // We generate a variable number of REVO accounts plus some non-REVO accounts.
  //   0 REVO  → status 'none'      → EXCLUDED (that is the bug condition, task 1)
  //   1 REVO  → status 'resolved'  → no popup, processing completes
  //  >=2 REVO → status 'ambiguous' → popup with exactly the REVO accounts
  // =========================================================================

  /** Distinct REVO accounts (these are the resolution candidates for a Revolut file). */
  function arbitraryRevoAccounts(): fc.Arbitrary<BankAccount[]> {
    return fc.array(
      fc.integer({ min: 1, max: 999 }),
      { minLength: 1, maxLength: 4 },
    ).map((ids) => {
      const unique = Array.from(new Set(ids));
      return unique.map((id) => ({
        rekeningNummer: `NL00REVO${id.toString().padStart(10, '0')}`,
        Account: `12${id.toString().padStart(2, '0')}`,
        administration: 'TestTenant',
      }));
    });
  }

  /** Distinct non-REVO accounts (never resolution candidates for a Revolut file). */
  function arbitraryNonRevoAccounts(): fc.Arbitrary<BankAccount[]> {
    return fc.array(
      fc.integer({ min: 1, max: 999 }),
      { minLength: 0, maxLength: 3 },
    ).map((ids) => {
      const unique = Array.from(new Set(ids));
      return unique.map((id) => ({
        rekeningNummer: `NL11RABO${id.toString().padStart(10, '0')}`,
        Account: `10${id.toString().padStart(2, '0')}`,
        administration: 'TestTenant',
      }));
    });
  }

  fcTest.prop(
    [arbitraryRevoAccounts(), arbitraryNonRevoAccounts()],
    { numRuns: 25 },
  )(
    'PROPERTY: a Revolut import behaves per its resolution status (resolved → no popup+process; ambiguous → popup with only the REVO candidates), with no error',
    async (revoAccounts, nonRevoAccounts) => {
      // Ensure Account keys are globally unique across the two groups so the
      // popup renders one button per candidate.
      const usedAccounts = new Set(revoAccounts.map((a) => a.Account));
      const filteredNonRevo = nonRevoAccounts.filter((a) => !usedAccounts.has(a.Account));
      const knownAccounts = [...revoAccounts, ...filteredNonRevo];

      const { unmount } = renderComponent(buildLookupData(knownAccounts));

      await selectAndProcess([revolutFile()]);

      // Never the bug-condition path here (>=1 REVO), so never the error.
      expect(noAccountErrorShown()).toBe(false);

      if (revoAccounts.length === 1) {
        // resolved → auto-select, no popup, processing completes.
        expect(screen.queryByRole('dialog')).toBeNull();
        expect(onTransactionsLoaded).toHaveBeenCalled();
      } else {
        // ambiguous → popup with EXACTLY the REVO candidates.
        expect(screen.queryByRole('dialog')).not.toBeNull();
        for (const revo of revoAccounts) {
          expect(screen.queryByText(new RegExp(revo.rekeningNummer))).not.toBeNull();
        }
        // Non-REVO accounts must NOT be offered as candidates.
        for (const nonRevo of filteredNonRevo) {
          expect(screen.queryByText(new RegExp(nonRevo.rekeningNummer))).toBeNull();
        }
        // Processing paused, not completed.
        expect(onTransactionsLoaded).not.toHaveBeenCalled();
      }

      // Reset for the next iteration.
      unmount();
      resetMocks();
    },
  );
});
