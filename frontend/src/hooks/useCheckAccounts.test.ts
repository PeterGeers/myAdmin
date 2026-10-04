/**
 * Tests for useCheckAccounts hook.
 *
 * Covers lookup fetch, check-accounts balance fetch (with/without end_date),
 * sequence-number check (gaps vs no gaps), row-expansion toggle, and the
 * error branch for each API call. apiService + context hooks mocked.
 */

import { vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { authenticatedGet } from '@/services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useCheckAccounts } from './useCheckAccounts';

vi.mock('@/services/apiService');
const mockGet = vi.mocked(authenticatedGet);

const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@chakra-ui/react');
  return { ...actual, useToast: () => mockToast };
});

vi.mock('@/context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'GoodwinSolutions' }),
}));
vi.mock('@/hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (k: string) => k, i18n: { language: 'nl' } }),
}));

const lookupBody = {
  success: true,
  accounts: ['1000'],
  descriptions: ['d'],
  bank_accounts: [{ Account: '1100', administration: 'T', rekeningNummer: 'NL01' }],
  credit_card_accounts: [{ cc_bank_iban: 'NL99', Account: '2000', card_number: '12', administration: 'T' }],
  exchange_rate_account: null,
};

/** Default GET resolver: lookups + opening-balance-date both succeed. */
function defaultGet(url: string) {
  if (url.startsWith('/api/banking/lookups')) {
    return Promise.resolve(createMockResponse({ body: lookupBody }));
  }
  if (url.startsWith('/api/banking/opening-balance-date')) {
    return Promise.resolve(
      createMockResponse({ body: { success: true, opening_balance_date: '2025-02-01' } }),
    );
  }
  return Promise.resolve(createMockResponse({ body: { success: true } }));
}

describe('useCheckAccounts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation(defaultGet as never);
  });

  it('fetches lookup data on mount and maps credit cards', async () => {
    const { result } = renderHook(() => useCheckAccounts());

    await waitFor(() => {
      expect(result.current.lookupData.accounts).toEqual(['1000']);
    });
    expect(result.current.lookupData.credit_card_accounts[0].iban).toBe('NL99');
    expect(mockGet).toHaveBeenCalledWith('/api/banking/lookups');
  });

  it('seeds sequenceStartDate from the opening-balance-date endpoint', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.openingBalanceDate).toBe('2025-02-01'));
    expect(result.current.sequenceStartDate).toBe('2025-02-01');
  });

  it('checkBankingAccounts stores balances and shows a success toast', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.lookupData.accounts.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(
        createMockResponse({ body: { success: true, count: 2, balances: [{ a: 1 }, { a: 2 }] } }),
      ),
    );

    await act(async () => {
      await result.current.checkBankingAccounts();
    });

    expect(result.current.bankingBalances).toHaveLength(2);
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
    const calledUrl = mockGet.mock.calls.find((c) => String(c[0]).includes('check-accounts'))?.[0];
    expect(String(calledUrl)).toContain('test_mode=false');
  });

  it('checkBankingAccounts shows an error toast on an unsuccessful response', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.lookupData.accounts.length).toBe(1));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(createMockResponse({ body: { success: false, error: 'nope' } })),
    );

    await act(async () => {
      await result.current.checkBankingAccounts();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
    expect(result.current.bankingBalances).toEqual([]);
  });

  it('checkBankingAccounts shows an error toast when the request rejects', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.lookupData.accounts.length).toBe(1));

    mockGet.mockImplementationOnce(() => Promise.reject(new Error('offline')));

    await act(async () => {
      await result.current.checkBankingAccounts();
    });

    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'error' }));
  });

  it('checkSequenceNumbers reports gaps with a warning toast', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.selectedAccount).toBe('1100-T'));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(
        createMockResponse({
          body: { success: true, has_gaps: true, sequence_issues: [{ gap: 1 }] },
        }),
      ),
    );

    await act(async () => {
      await result.current.checkSequenceNumbers();
    });

    expect(result.current.sequenceResult?.has_gaps).toBe(true);
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'warning' }));
    const url = mockGet.mock.calls.find((c) => String(c[0]).includes('check-sequence'))?.[0];
    expect(String(url)).toContain('account_code=1100');
    expect(String(url)).toContain('administration=T');
  });

  it('checkSequenceNumbers reports a clean result with a success toast', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.selectedAccount).toBe('1100-T'));

    mockGet.mockImplementationOnce(() =>
      Promise.resolve(
        createMockResponse({ body: { success: true, has_gaps: false, sequence_issues: [] } }),
      ),
    );

    await act(async () => {
      await result.current.checkSequenceNumbers();
    });

    expect(result.current.sequenceResult?.has_gaps).toBe(false);
    expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
  });

  it('toggleRowExpansion adds then removes a key', async () => {
    const { result } = renderHook(() => useCheckAccounts());
    await waitFor(() => expect(result.current.lookupData.accounts.length).toBe(1));

    act(() => result.current.toggleRowExpansion('row-1'));
    expect(result.current.expandedRows.has('row-1')).toBe(true);

    act(() => result.current.toggleRowExpansion('row-1'));
    expect(result.current.expandedRows.has('row-1')).toBe(false);
  });
});
