/**
 * Tests for useBankingState hook + its stateless helpers.
 *
 * Covers:
 *  - formatAmount (Dutch-locale currency formatting, exact amount handling)
 *  - mapLookupData (backend → frontend credit-card field mapping)
 *  - fetchLookupData state transition (success + error branch)
 *  - modal open handlers (edit / insert)
 *
 * apiService is mocked so no real network/auth is exercised.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { authenticatedGet } from '../services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useBankingState, formatAmount, mapLookupData } from './useBankingState';
import type { Transaction } from '../components/BankingProcessor.types';

// ─── Mocks ──────────────────────────────────────────────────────────────────

vi.mock('../services/apiService');
const mockGet = vi.mocked(authenticatedGet);

const mockUseTenant = vi.fn();
vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant(),
}));

vi.mock('./useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key, i18n: { language: 'nl' } }),
}));

vi.mock('./useAccountLookup', () => ({
  useAccountLookup: () => ({ accounts: [] }),
}));

// ─── Pure helper tests ────────────────────────────────────────────────────────

describe('formatAmount', () => {
  it('formats a positive amount with Dutch locale and 2 decimals', () => {
    // nl-NL uses "." as thousands sep and "," as decimal sep
    expect(formatAmount(1234.5)).toBe('€1.234,50');
  });

  it('formats zero correctly', () => {
    expect(formatAmount(0)).toBe('€0,00');
  });

  it('coerces NaN/invalid input to 0', () => {
    expect(formatAmount(Number.NaN)).toBe('€0,00');
    // @ts-expect-error — deliberately passing a non-number
    expect(formatAmount(undefined)).toBe('€0,00');
  });

  it('formats negative amounts preserving the sign', () => {
    expect(formatAmount(-99.99)).toBe('€-99,99');
  });
});

describe('mapLookupData', () => {
  it('maps credit_card_accounts fields, preferring cc_bank_iban over iban', () => {
    const result = mapLookupData({
      accounts: ['1000'],
      descriptions: ['Cash'],
      bank_accounts: [{ rekeningNummer: 'NL01', Account: '1100', administration: 'T' }],
      credit_card_accounts: [
        { cc_bank_iban: 'NL99', iban: 'NL88', Account: '2000', card_number: '1234', administration: 'T' },
      ],
      exchange_rate_account: '9999',
    });

    expect(result.credit_card_accounts[0]).toEqual({
      iban: 'NL99',
      Account: '2000',
      card_number: '1234',
      administration: 'T',
    });
    expect(result.accounts).toEqual(['1000']);
    expect(result.exchange_rate_account).toBe('9999');
  });

  it('falls back to iban when cc_bank_iban is absent and defaults missing fields to empty string', () => {
    const result = mapLookupData({
      accounts: [],
      descriptions: [],
      bank_accounts: [],
      credit_card_accounts: [{ iban: 'NL77' }],
      exchange_rate_account: null,
    });

    expect(result.credit_card_accounts[0]).toEqual({
      iban: 'NL77',
      Account: '',
      card_number: '',
      administration: '',
    });
  });

  it('handles a missing credit_card_accounts array gracefully', () => {
    const result = mapLookupData({
      accounts: [],
      descriptions: [],
      bank_accounts: [],
      // @ts-expect-error — simulate backend omitting the field
      credit_card_accounts: undefined,
      exchange_rate_account: null,
    });
    expect(result.credit_card_accounts).toEqual([]);
  });
});

// ─── Hook tests ────────────────────────────────────────────────────────────────

describe('useBankingState', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockUseTenant.mockReturnValue({ currentTenant: 'GoodwinSolutions' });
    // default lookup success
    mockGet.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          accounts: ['1000'],
          descriptions: ['desc'],
          bank_accounts: [],
          credit_card_accounts: [],
          exchange_rate_account: null,
        },
      }),
    );
  });

  it('fetches lookup data on mount and hits the correct endpoint', async () => {
    const { result } = renderHook(() => useBankingState());

    await waitFor(() => {
      expect(result.current.lookupData.accounts).toEqual(['1000']);
    });

    expect(mockGet).toHaveBeenCalledWith('/api/banking/lookups');
  });

  it('does not update lookup state when the response is unsuccessful', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: false } }));

    const { result } = renderHook(() => useBankingState());

    // Give effects a chance to run
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.lookupData.accounts).toEqual([]);
  });

  it('swallows API errors without throwing (error branch)', async () => {
    mockGet.mockRejectedValue(new Error('network down'));
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(() => useBankingState());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.lookupData.accounts).toEqual([]);
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it('openEditModal clones the record, exits insert mode and clears modal error', () => {
    const { result } = renderHook(() => useBankingState());
    const record = { row_id: 1, TransactionAmount: 50 } as unknown as Transaction;

    act(() => {
      result.current.openEditModal(record);
    });

    expect(result.current.editingRecord).toEqual(record);
    expect(result.current.editingRecord).not.toBe(record); // cloned
    expect(result.current.isInsertMode).toBe(false);
    expect(result.current.isOpen).toBe(true);
    expect(result.current.modalError).toBe('');
  });

  it('openInsertModal seeds a blank record with the stored tenant and insert mode', () => {
    localStorage.setItem('selectedTenant', 'MyTenant');
    const { result } = renderHook(() => useBankingState());

    act(() => {
      result.current.openInsertModal();
    });

    expect(result.current.isInsertMode).toBe(true);
    expect(result.current.isOpen).toBe(true);
    expect(result.current.editingRecord?.Administration).toBe('MyTenant');
    expect(result.current.editingRecord?.TransactionAmount).toBe(0);
    expect(result.current.editingRecord?.ID).toBe(0);
  });

  it('openInsertModal falls back to PeterPrive when no tenant is stored', () => {
    const { result } = renderHook(() => useBankingState());

    act(() => {
      result.current.openInsertModal();
    });

    expect(result.current.editingRecord?.Administration).toBe('PeterPrive');
  });
});
