/**
 * Bug Condition Exploration Test — Ambiguous Account Resolution
 *
 * Property 1: Bug Condition — Multiple candidate accounts, no dialog shown
 *
 * CRITICAL: This test encodes the EXPECTED (correct) behavior.
 * On UNFIXED code it MUST FAIL — failure confirms the bug exists.
 * After the fix is applied, this same test validates the fix when it passes.
 *
 * Bug condition C(X): resolveAccountCandidates yields |candidates| > 1
 * Expected behavior: BankingFileUpload shows an account selection dialog
 * and the user-selected account is used for Ref1 and Account fields.
 *
 * **Validates: Requirements 1.1, 2.2, 2.3**
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, expect, vi, beforeEach, afterEach } from 'vitest';
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

// Import component after mocks
import BankingFileUpload from '../../BankingFileUpload';
import type { LookupData } from '../../BankingProcessor.types';
import { createMockResponse } from '../../../test-utils/mockHelpers';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a bank account with REVO in the IBAN */
function arbitraryRevolutAccount(): fc.Arbitrary<{ rekeningNummer: string; Account: string; administration: string }> {
  return fc.tuple(
    // Account number (4 digits)
    fc.integer({ min: 1000, max: 9999 }),
    // IBAN with REVO (varying structure)
    fc.stringMatching(/^NL[0-9]{2}REVO[0-9]{10}$/)
  ).map(([acctNum, iban]) => ({
    rekeningNummer: iban,
    Account: acctNum.toString(),
    administration: 'TestTenant',
  }));
}

/** Generate a set of 2-5 Revolut accounts (the bug condition: >1 candidates) */
function arbitraryMultipleRevolutAccounts(): fc.Arbitrary<Array<{ rekeningNummer: string; Account: string; administration: string }>> {
  return fc.array(arbitraryRevolutAccount(), { minLength: 2, maxLength: 5 })
    // Ensure unique account numbers
    .map(accounts => {
      const seen = new Set<string>();
      return accounts.filter(a => {
        if (seen.has(a.Account)) return false;
        seen.add(a.Account);
        return true;
      });
    })
    // Re-filter to ensure at least 2
    .filter(accounts => accounts.length >= 2);
}

/**
 * Create a minimal Revolut CSV file content (Dutch format).
 * The content is valid enough for the component to attempt processing.
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

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

describe('Bug Condition Exploration — Account Resolution Ambiguity', () => {
  const defaultOnTransactionsLoaded = vi.fn();
  const defaultSetLoading = vi.fn();
  const defaultSetMessage = vi.fn();
  const defaultSetLookupData = vi.fn();
  const defaultMapLookupData = vi.fn((data: any) => data);

  function buildLookupData(bankAccounts: Array<{ rekeningNummer: string; Account: string; administration: string }>): LookupData {
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

    // Mock sequence check to return no duplicates
    mockAuthenticatedPost.mockResolvedValue(
      createMockResponse({ body: { success: true, duplicates: [] } })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Concrete test: 2 Revolut accounts → must show selection dialog
  // -------------------------------------------------------------------------

  it('should show account selection dialog when 2 Revolut accounts are configured', async () => {
    const accounts = [
      { rekeningNummer: 'NL08REVO7549383472', Account: '1021', administration: 'TestTenant' },
      { rekeningNummer: 'NL44REVO9988776655', Account: '1022', administration: 'TestTenant' },
    ];
    const lookupData = buildLookupData(accounts);
    renderComponent(lookupData);

    // Simulate file selection
    const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(inputEl).not.toBeNull();

    const file = createRevolutFile(createRevolutFileContent());

    await act(async () => {
      fireEvent.change(inputEl, { target: { files: [file] } });
    });

    // Click process button
    const processButton = await screen.findByText('fileProcessing.processFiles');
    await act(async () => {
      fireEvent.click(processButton);
    });

    // Wait for processing to complete
    await waitFor(() => {
      expect(defaultSetLoading).toHaveBeenCalledWith(false);
    });

    // BUG CONDITION ASSERTION:
    // With multiple Revolut accounts, the system MUST show an account selection dialog.
    // On unfixed code, no dialog exists — this assertion will FAIL, proving the bug.
    const dialog = screen.queryByRole('dialog');
    expect(dialog).not.toBeNull();

    // The dialog must contain account information for user to choose from
    if (dialog) {
      // Dialog should contain the account selection title
      expect(screen.getByText(/accountSelection\.title|Select Bank Account/i)).toBeDefined();
      // Both account IBANs should be shown as options
      expect(screen.getByText(/NL08REVO7549383472/)).toBeDefined();
      expect(screen.getByText(/NL44REVO9988776655/)).toBeDefined();
    }
  });

  // -------------------------------------------------------------------------
  // Property-based test: random sets of 2-5 Revolut accounts
  // -------------------------------------------------------------------------

  fcTest.prop(
    [arbitraryMultipleRevolutAccounts()],
    { numRuns: 20 },
  )(
    'PROPERTY: for all sets of 2+ Revolut accounts, processing MUST show account selection dialog',
    async (revolutAccounts) => {
      const lookupData = buildLookupData(revolutAccounts);
      const { unmount } = renderComponent(lookupData);

      // Simulate file selection
      const inputEl = document.querySelector('input[type="file"]') as HTMLInputElement;
      if (!inputEl) {
        // If the component didn't render an input, the test framework has an issue
        // but we shouldn't fail silently — assert it exists
        expect(inputEl).not.toBeNull();
        return;
      }

      const file = createRevolutFile(createRevolutFileContent());

      await act(async () => {
        fireEvent.change(inputEl, { target: { files: [file] } });
      });

      // Click process button
      const processButton = screen.getByText('fileProcessing.processFiles');
      await act(async () => {
        fireEvent.click(processButton);
      });

      // Wait for processing to settle
      await waitFor(() => {
        expect(defaultSetLoading).toHaveBeenCalledWith(false);
      });

      // BUG CONDITION: multiple candidates → dialog MUST be shown
      // On unfixed code: no dialog exists → this FAILS → confirms bug
      const dialog = screen.queryByRole('dialog');
      expect(dialog).not.toBeNull();

      // If dialog is present, verify it offers account selection
      if (dialog) {
        // At least one of the REVO account IBANs should be visible
        const anyAccountVisible = revolutAccounts.some(
          acct => screen.queryByText(new RegExp(acct.rekeningNummer)) !== null
        );
        expect(anyAccountVisible).toBe(true);
      }

      // Cleanup for property-based test iteration
      unmount();
      vi.clearAllMocks();
      localStorageMock.getItem.mockReturnValue('TestTenant');
      mockAuthenticatedPost.mockResolvedValue(
        createMockResponse({ body: { success: true, duplicates: [] } })
      );
    },
  );
});
