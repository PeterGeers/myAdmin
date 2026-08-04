/**
 * useCheckAccounts Hook
 *
 * Standalone hook for the Check Accounts page.
 * Encapsulates data fetching, state management, and API calls for
 * checking banking account balances and sequence numbers.
 *
 * Extracted from useBankingState + useBankingUpload to allow
 * CheckAccountsPage to be self-contained.
 *
 * @module hooks/useCheckAccounts
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-3
 */

import { useCallback, useEffect, useState } from 'react';
import { useToast } from '@chakra-ui/react';
import { authenticatedGet } from '@/services/apiService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import { useTenant } from '@/context/TenantContext';
import type { BankingBalance, LookupData } from '@/components/BankingProcessor.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SequenceResult {
  check_type: string;
  has_gaps: boolean;
  sequence_issues: Array<{
    expected: string;
    found: string;
    gap: number;
    date?: string;
    description?: string;
  }>;
  account_code: string;
  administration: string;
  iban: string;
  start_date: string;
  total_transactions: number;
  first_sequence?: number;
  last_sequence?: number;
  message?: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCheckAccounts() {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const toast = useToast();

  // --- State ---
  const [bankingBalances, setBankingBalances] = useState<BankingBalance[]>([]);
  const [checkingAccounts, setCheckingAccounts] = useState(false);
  const [sequenceResult, setSequenceResult] = useState<SequenceResult | null>(null);
  const [checkingSequence, setCheckingSequence] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [endDate, setEndDate] = useState('');
  const [sequenceStartDate, setSequenceStartDate] = useState('2025-01-01');
  const [openingBalanceDate, setOpeningBalanceDate] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [lookupData, setLookupData] = useState<LookupData>({
    accounts: [],
    descriptions: [],
    bank_accounts: [],
    credit_card_accounts: [],
    exchange_rate_account: null,
  });
  const [testMode] = useState(false);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------

  const fetchLookupData = useCallback(async () => {
    try {
      const response = await authenticatedGet('/api/banking/lookups');
      const data = await response.json();
      if (data.success) {
        setLookupData({
          accounts: data.accounts,
          descriptions: data.descriptions,
          bank_accounts: data.bank_accounts,
          credit_card_accounts: (data.credit_card_accounts || []).map(
            (cc: { cc_bank_iban?: string; iban?: string; Account?: string; card_number?: string; administration?: string }) => ({
              iban: cc.cc_bank_iban || cc.iban || '',
              Account: cc.Account || '',
              card_number: cc.card_number || '',
              administration: cc.administration || '',
            }),
          ),
          exchange_rate_account: data.exchange_rate_account,
        });
      }
    } catch (error) {
      console.error('Error fetching lookup data:', error);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Check Accounts API
  // ---------------------------------------------------------------------------

  const checkBankingAccounts = useCallback(async () => {
    try {
      setCheckingAccounts(true);
      const params = new URLSearchParams({ test_mode: testMode.toString() });
      if (endDate) params.append('end_date', endDate);

      const response = await authenticatedGet(`/api/banking/check-accounts?${params}`);
      const data = await response.json();

      if (data.success) {
        setBankingBalances(data.balances);
        toast({
          title: endDate
            ? t('messages.foundAccountsAsOf', { count: data.count, date: endDate })
            : t('messages.foundAccounts', { count: data.count }),
          status: 'success',
          duration: 3000,
        });
      } else {
        toast({
          title: t('messages.errorGeneric', { error: data.error }),
          status: 'error',
          duration: 4000,
        });
      }
    } catch (error) {
      toast({
        title: t('messages.errorCheckingAccounts', { error: String(error) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setCheckingAccounts(false);
    }
  }, [testMode, endDate, t, toast]);

  // ---------------------------------------------------------------------------
  // Check Sequence API
  // ---------------------------------------------------------------------------

  const checkSequenceNumbers = useCallback(async () => {
    try {
      setCheckingSequence(true);
      const [account_code, administration] = selectedAccount.split('-');
      const params = new URLSearchParams({
        test_mode: testMode.toString(),
        account_code,
        administration,
        start_date: sequenceStartDate,
      });

      const response = await authenticatedGet(`/api/banking/check-sequence?${params}`);
      const data = await response.json();

      if (data.success) {
        setSequenceResult(data);
        const gapMsg = data.has_gaps
          ? t('messages.gapsFound', { count: data.sequence_issues.length })
          : t('messages.noGapsFound');
        toast({
          title: t('messages.sequenceCheckComplete', { account: account_code, administration }) + ` - ${gapMsg}`,
          status: data.has_gaps ? 'warning' : 'success',
          duration: 4000,
        });
      } else {
        toast({
          title: t('messages.errorGeneric', { error: data.error }),
          status: 'error',
          duration: 4000,
        });
      }
    } catch (error) {
      toast({
        title: t('messages.errorCheckingSequence', { error: String(error) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setCheckingSequence(false);
    }
  }, [testMode, selectedAccount, sequenceStartDate, t, toast]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const toggleRowExpansion = useCallback((key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const form = e.currentTarget.closest('form');
      if (form) {
        const inputs = Array.from(
          form.querySelectorAll('input, select, textarea'),
        ) as HTMLElement[];
        const currentIndex = inputs.indexOf(e.currentTarget as HTMLElement);
        const nextInput = inputs[currentIndex + 1];
        if (nextInput) nextInput.focus();
      }
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Fetch lookup data on mount
  useEffect(() => {
    fetchLookupData();
  }, [fetchLookupData]);

  // Reset state and refetch on tenant change
  useEffect(() => {
    if (currentTenant) {
      setBankingBalances([]);
      setSequenceResult(null);
      setSelectedAccount('');
      fetchLookupData();
    }
  }, [currentTenant, fetchLookupData]);

  // Set initial selectedAccount when lookupData changes
  useEffect(() => {
    if (lookupData.bank_accounts.length > 0 && !selectedAccount) {
      const firstAccount = lookupData.bank_accounts[0];
      setSelectedAccount(`${firstAccount.Account}-${firstAccount.administration}`);
    }
  }, [lookupData.bank_accounts, selectedAccount]);

  // Fetch opening balance date
  useEffect(() => {
    const fetchOpeningBalanceDate = async () => {
      try {
        const params = new URLSearchParams({ test_mode: testMode.toString() });
        const response = await authenticatedGet(`/api/banking/opening-balance-date?${params}`);
        const data = await response.json();
        if (data.success && data.opening_balance_date) {
          setOpeningBalanceDate(data.opening_balance_date);
          setSequenceStartDate(data.opening_balance_date);
        } else {
          setOpeningBalanceDate(null);
        }
      } catch (error) {
        console.error('Error fetching opening balance date:', error);
        setOpeningBalanceDate(null);
      }
    };
    fetchOpeningBalanceDate();
  }, [currentTenant, testMode]);

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    t,
    // State
    bankingBalances,
    checkingAccounts,
    sequenceResult,
    checkingSequence,
    expandedRows,
    endDate,
    setEndDate,
    sequenceStartDate,
    setSequenceStartDate,
    openingBalanceDate,
    selectedAccount,
    setSelectedAccount,
    lookupData,
    // Actions
    checkBankingAccounts,
    checkSequenceNumbers,
    toggleRowExpansion,
    handleKeyDown,
  };
}
