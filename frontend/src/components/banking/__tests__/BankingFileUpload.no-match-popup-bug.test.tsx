/**
 * Bug Condition Exploration Test — No-match import fails to open the popup
 *
 * Spec: revolut-iban-select-popup-fix
 * Property 1: Bug Condition — a non-credit-card import whose account resolution
 * returns `status: 'none'` (no configured account matches) should FALL BACK to the
 * account-selection popup populated with ALL of the tenant's known bank accounts,
 * instead of aborting with the "no account configured" error.
 *
 * CRITICAL: This test encodes the EXPECTED (post-fix) behavior.
 * On UNFIXED code it MUST FAIL — the `resolution.status === 'none'` branch of
 * `processFiles` calls `setMessage(t('accountSelection.noAccountConfigured'))` and
 * returns WITHOUT `setAccountCandidates(...)` / `setShowAccountDialog(true)`, so no
 * dialog opens. That failure confirms the bug exists.
 * DO NOT fix the test or the code here — the fix lands in a later task and this same
 * test then validates it when it passes.
 *
 * Bug condition C(X): non-CC file where resolveAccountCandidates(...).status === 'none'
 * AND currentLookupData.bank_accounts is non-empty.
 * Expected behavior: the account-selection popup opens listing ALL known bank
 * accounts, and the noAccountConfigured error is NOT shown.
 *
 * Cases covered (design Examples):
 *   (a) two Revolut CSVs, no REVO account
 *   (b) single Revolut CSV, no REVO account
 *   (c) a Rabobank/IBAN file whose IBAN matches no configured rekeningNummer
 * Plus a scoped property-based test over reasonable non-empty known-account lists.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**
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

/** A Revolut file — name starts with `account-statement`, so it matches by REVO. */
function revolutFile(name = 'account-statement_2026-08-01_2026-09-25_en-us_468cd1.csv'): File {
  return new File([revolutContent()], name, { type: 'text/csv' });
}

/**
 * Minimal Rabobank-style CSV whose column-0 IBAN is `iban`. When no configured
 * rekeningNummer equals `iban`, resolveAccountCandidates returns status: 'none'.
 */
function rabobankFile(iban: string, name = 'rabobank_2026.csv'): File {
  const header = 'IBAN,Munt,Volgnr,Datum,Rentedatum,Bedrag,Saldo,Tegenrekening';
  const row = `${iban},EUR,1,2026-04-16,2026-04-16,-29.06,1250.00,NL00OTHR0000000000`;
  return new File([`${header}\n${row}`], name, { type: 'text/csv' });
}

// ---------------------------------------------------------------------------
// Test scaffolding
// ---------------------------------------------------------------------------

describe('Bug Condition Exploration — no-match import must open the known-accounts popup', () => {
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

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('TestTenant');
    // Sequence check returns no duplicates (only reached if processing continues).
    mockAuthenticatedPost.mockResolvedValue(
      createMockResponse({ body: { success: true, duplicates: [] } })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Case (a): two Revolut CSVs, tenant has NO REVO account
  // -------------------------------------------------------------------------

  it('(a) two Revolut CSVs with no REVO account → opens popup with all known accounts, no error', async () => {
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: 'NL11RABO0111111111', Account: '1010', administration: 'TestTenant' },
      { rekeningNummer: 'NL22INGB0222222222', Account: '1020', administration: 'TestTenant' },
      { rekeningNummer: 'NL33ABNA0333333333', Account: '1030', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts));

    await selectAndProcess([
      revolutFile('account-statement_2026-08-01_2026-09-25_en-us_468cd1.csv'),
      revolutFile('account-statement_2026-08-01_2026-09-25_en-us_4428f6.csv'),
    ]);

    // Popup MUST open (showAccountDialog true → Modal renders role="dialog").
    const dialog = screen.queryByRole('dialog');
    expect(dialog).not.toBeNull();

    // Populated with ALL of the tenant's known bank accounts.
    for (const acct of knownAccounts) {
      expect(screen.getByText(new RegExp(acct.rekeningNummer))).toBeDefined();
    }

    // And the "no account configured" error must NOT be shown.
    expect(noAccountErrorShown()).toBe(false);
  });

  // -------------------------------------------------------------------------
  // Case (b): single Revolut CSV, tenant has NO REVO account
  // -------------------------------------------------------------------------

  it('(b) single Revolut CSV with no REVO account → opens popup with all known accounts, no error', async () => {
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: 'NL11RABO0111111111', Account: '1010', administration: 'TestTenant' },
      { rekeningNummer: 'NL22INGB0222222222', Account: '1020', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts));

    await selectAndProcess([revolutFile()]);

    const dialog = screen.queryByRole('dialog');
    expect(dialog).not.toBeNull();
    for (const acct of knownAccounts) {
      expect(screen.getByText(new RegExp(acct.rekeningNummer))).toBeDefined();
    }
    expect(noAccountErrorShown()).toBe(false);
  });

  // -------------------------------------------------------------------------
  // Case (c): Rabobank/IBAN file whose IBAN matches no configured rekeningNummer
  // -------------------------------------------------------------------------

  it('(c) Rabobank/IBAN file matching no configured account → opens popup with all known accounts, no error', async () => {
    const knownAccounts: BankAccount[] = [
      { rekeningNummer: 'NL11RABO0111111111', Account: '1010', administration: 'TestTenant' },
      { rekeningNummer: 'NL22INGB0222222222', Account: '1020', administration: 'TestTenant' },
    ];
    renderComponent(buildLookupData(knownAccounts));

    // File IBAN does not equal any configured rekeningNummer → status 'none'.
    await selectAndProcess([rabobankFile('NL99UNKN0999999999')]);

    const dialog = screen.queryByRole('dialog');
    expect(dialog).not.toBeNull();
    for (const acct of knownAccounts) {
      expect(screen.getByText(new RegExp(acct.rekeningNummer))).toBeDefined();
    }
    expect(noAccountErrorShown()).toBe(false);
  });

  // -------------------------------------------------------------------------
  // Scoped property-based test: any non-empty known-account list with no REVO
  // account and a Revolut file (status 'none') must open the popup with ALL of
  // those accounts and never show the error.
  // -------------------------------------------------------------------------

  /** A non-REVO bank account (so a Revolut file resolves to 'none'). */
  function arbitraryNonRevoAccount(): fc.Arbitrary<BankAccount> {
    return fc.tuple(
      fc.integer({ min: 1000, max: 9999 }),
      // IBAN without the REVO marker.
      fc.stringMatching(/^NL[0-9]{2}(RABO|INGB|ABNA|SNSB)0[0-9]{9}$/)
    ).map(([acctNum, iban]) => ({
      rekeningNummer: iban,
      Account: acctNum.toString(),
      administration: 'TestTenant',
    }));
  }

  /** 1–5 unique-by-Account, unique-by-IBAN, non-REVO known accounts. */
  function arbitraryKnownAccounts(): fc.Arbitrary<BankAccount[]> {
    return fc.array(arbitraryNonRevoAccount(), { minLength: 1, maxLength: 5 })
      .map((accounts) => {
        const seenAcct = new Set<string>();
        const seenIban = new Set<string>();
        return accounts.filter((a) => {
          if (seenAcct.has(a.Account) || seenIban.has(a.rekeningNummer)) return false;
          seenAcct.add(a.Account);
          seenIban.add(a.rekeningNummer);
          return true;
        });
      })
      .filter((accounts) => accounts.length >= 1);
  }

  fcTest.prop([arbitraryKnownAccounts()], { numRuns: 20 })(
    'PROPERTY: for any non-empty non-REVO known-account list, a Revolut import (status none) opens the popup with all known accounts and shows no error',
    async (knownAccounts) => {
      const { unmount } = renderComponent(buildLookupData(knownAccounts));

      await selectAndProcess([revolutFile()]);

      // Popup MUST open on the 'none' fallback.
      const dialog = screen.queryByRole('dialog');
      expect(dialog).not.toBeNull();

      // Every known account must be offered.
      const allAccountsVisible = knownAccounts.every(
        (acct) => screen.queryByText(new RegExp(acct.rekeningNummer)) !== null
      );
      expect(allAccountsVisible).toBe(true);

      // The no-account-configured error must never be shown.
      expect(noAccountErrorShown()).toBe(false);

      // Reset for the next iteration.
      unmount();
      vi.clearAllMocks();
      localStorageMock.getItem.mockReturnValue('TestTenant');
      mockAuthenticatedPost.mockResolvedValue(
        createMockResponse({ body: { success: true, duplicates: [] } })
      );
    },
  );
});
