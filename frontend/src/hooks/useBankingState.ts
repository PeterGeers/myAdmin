/**
 * useBankingState Hook
 *
 * Core shared state for the Banking Processor: transactions, mutaties,
 * lookup data, filter options, modal state, filterable table configurations,
 * and tenant-sync effects.
 */

import { useCallback, useEffect, useState } from 'react';
import { useDisclosure } from '@chakra-ui/react';
import { authenticatedGet } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTypedTranslation } from './useTypedTranslation';
import { useAccountLookup } from './useAccountLookup';
import { useFilterableTable } from './useFilterableTable';
import type { Transaction, LookupData } from '../components/BankingProcessor.types';
import type { RefSummaryRow, TransactionRow } from './useBankingUpload';

// ---------------------------------------------------------------------------
// Utility helpers (stateless)
// ---------------------------------------------------------------------------

/** Raw credit card account shape from backend */
interface CreditCardAccountRaw {
  cc_bank_iban?: string;
  iban?: string;
  Account?: string;
  card_number?: string;
  administration?: string;
}

/** Lookup data with optional credit card accounts from backend */
interface BankingLookupData {
  credit_card_accounts?: CreditCardAccountRaw[];
  [key: string]: unknown;
}

/** Map backend credit_card_accounts fields to frontend interface */
export const mapLookupData = (data: BankingLookupData): BankingLookupData => {
  if (data.credit_card_accounts) {
    data.credit_card_accounts = data.credit_card_accounts.map((cc) => ({
      iban: cc.cc_bank_iban || cc.iban || '',
      Account: cc.Account,
      card_number: cc.card_number || '',
      administration: cc.administration,
    }));
  }
  return data;
};

/** Format a number as Dutch-locale currency */
export const formatAmount = (amount: number): string => {
  const num = Number(amount) || 0;
  return `€${num.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
};

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBankingState() {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const { accounts: chartAccounts } = useAccountLookup();

  // --- Core transaction state ---
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [mutaties, setMutaties] = useState<Transaction[]>([]);
  const [testMode] = useState(false); // Always use production mode
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [modalError, setModalError] = useState('');
  const [lookupData, setLookupData] = useState<LookupData>({
    accounts: [],
    descriptions: [],
    bank_accounts: [],
    credit_card_accounts: [],
    exchange_rate_account: null,
  });
  const [filterOptions, setFilterOptions] = useState<{ years: string[]; administrations: string[] }>({
    years: [],
    administrations: [],
  });
  const [mutatiesFilters, setMutatiesFilters] = useState({
    years: [new Date().getFullYear().toString()],
  });

  // --- Check Accounts UI state (not data) ---
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [endDate, setEndDate] = useState('');
  const [sequenceStartDate, setSequenceStartDate] = useState('2025-01-01');
  const [openingBalanceDate, setOpeningBalanceDate] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState('');

  // --- Check Reference filter state ---
  const [checkRefFilters, setCheckRefFilters] = useState({
    administration: currentTenant || 'GoodwinSolutions',
    ledger: 'all',
    referenceNumber: 'all',
  });

  // --- STR Channel filter state ---
  const [strChannelFilters, setStrChannelFilters] = useState({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    administration: currentTenant || 'GoodwinSolutions',
  });

  // --- Modal state ---
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<Transaction | null>(null);
  const [isInsertMode, setIsInsertMode] = useState(false);

  // --- Filterable table hooks for Check Reference ---
  const [refSummaryDataForTable, setRefSummaryDataForTable] = useState<RefSummaryRow[]>([]);
  const [refDetailsDataForTable, setRefDetailsDataForTable] = useState<TransactionRow[]>([]);

  const REF_SUMMARY_FILTERS: Record<string, string> = { ReferenceNumber: '', transaction_count: '', total_amount: '' };
  const REF_DETAILS_FILTERS: Record<string, string> = { TransactionNumber: '', TransactionDate: '', Amount: '', TransactionDescription: '' };

  const {
    filters: refSummaryFilters,
    setFilter: setRefSummaryFilter,
    handleSort: handleRefSummarySort,
    sortField: refSummarySortField,
    sortDirection: refSummarySortDirection,
    processedData: processedRefSummary,
  } = useFilterableTable(refSummaryDataForTable, {
    initialFilters: REF_SUMMARY_FILTERS,
    defaultSort: { field: 'ReferenceNumber', direction: 'asc' },
  });

  const {
    filters: refDetailsFilters,
    setFilter: setRefDetailsFilter,
    handleSort: handleRefDetailsSort,
    sortField: refDetailsSortField,
    sortDirection: refDetailsSortDirection,
    processedData: processedRefDetails,
  } = useFilterableTable(refDetailsDataForTable, {
    initialFilters: REF_DETAILS_FILTERS,
    defaultSort: { field: 'TransactionDate', direction: 'desc' },
  });

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

  const copyToClipboard = useCallback(
    (text: string) => {
      navigator.clipboard.writeText(text).then(() => {
        setMessage(t('messages.copiedToClipboard'));
        setTimeout(() => setMessage(''), 2000);
      });
    },
    [t]
  );

  const handleRef3Click = useCallback(
    async (ref3: string) => {
      if (ref3.startsWith('https://drive.goo')) {
        window.open(ref3, '_blank');
      } else if (ref3 && !ref3.startsWith('http')) {
        try {
          const resp = await authenticatedGet(
            `/api/storage/presigned-url?key=${encodeURIComponent(ref3)}`,
            { tenant: currentTenant || undefined }
          );
          const data = await resp.json();
          if (data.success && data.url) {
            window.open(data.url, '_blank');
          } else {
            copyToClipboard(ref3);
          }
        } catch {
          copyToClipboard(ref3);
        }
      } else {
        copyToClipboard(ref3);
      }
    },
    [currentTenant, copyToClipboard]
  );

  const openEditModal = useCallback(
    (record: Transaction) => {
      setEditingRecord({ ...record });
      setIsInsertMode(false);
      setModalError('');
      onOpen();
    },
    [onOpen]
  );

  const openInsertModal = useCallback(() => {
    setModalError('');
    const tenant = localStorage.getItem('selectedTenant') || 'PeterPrive';
    const newRecord: Transaction = {
      ID: 0,
      row_id: Date.now(),
      TransactionNumber: '',
      TransactionDate: new Date().toISOString().split('T')[0],
      TransactionDescription: '',
      TransactionAmount: 0,
      Administration: tenant,
      Debet: '',
      Credit: '',
      ReferenceNumber: '',
      Ref1: '',
      Ref2: '',
      Ref3: '',
      Ref4: '',
    };
    setEditingRecord(newRecord);
    setIsInsertMode(true);
    onOpen();
  }, [onOpen]);

  // ---------------------------------------------------------------------------
  // API handlers — Lookup & Mutaties
  // ---------------------------------------------------------------------------

  const fetchLookupData = useCallback(async () => {
    try {
      const response = await authenticatedGet('/api/banking/lookups');
      const data = await response.json();
      if (data.success) setLookupData(mapLookupData(data));
    } catch (error) {
      console.error('Error fetching lookup data:', error);
    }
  }, []);

  const fetchMutaties = useCallback(async () => {
    try {
      const tenant = localStorage.getItem('selectedTenant');
      if (!tenant) {
        console.error('No tenant selected for mutaties fetch');
        return;
      }
      const params = new URLSearchParams({
        years: mutatiesFilters.years.join(','),
        administration: tenant,
        limit: '99999',
      });
      const response = await authenticatedGet(`/api/banking/mutaties?${params}`);
      const data = await response.json();
      if (data.success) setMutaties(data.mutaties);
    } catch (error) {
      console.error('Error fetching mutaties:', error);
    }
  }, [mutatiesFilters]);

  const fetchFilterOptions = useCallback(async () => {
    try {
      const response = await authenticatedGet('/api/banking/filter-options');
      const data = await response.json();
      if (data.success) setFilterOptions(data);
    } catch (error) {
      console.error('Error fetching filter options:', error);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  useEffect(() => {
    fetchLookupData();
    fetchFilterOptions();
    fetchMutaties();
  }, [testMode, fetchLookupData, fetchFilterOptions, fetchMutaties]);

  useEffect(() => {
    fetchMutaties();
  }, [fetchMutaties]);

  // Auto-refresh when tenant changes
  useEffect(() => {
    if (currentTenant) {
      fetchMutaties();
      fetchLookupData();
      setSelectedAccount('');
    }
  }, [currentTenant, fetchMutaties, fetchLookupData]);

  // Fetch opening balance date based on annual closure
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

  // Set initial selectedAccount when lookupData changes
  useEffect(() => {
    if (lookupData.bank_accounts.length > 0 && !selectedAccount) {
      const firstAccount = lookupData.bank_accounts[0];
      setSelectedAccount(`${firstAccount.Account}-${firstAccount.administration}`);
    }
  }, [lookupData.bank_accounts, selectedAccount]);

  // Update checkRefFilters when tenant changes
  useEffect(() => {
    if (currentTenant) {
      setCheckRefFilters((prev) => ({ ...prev, administration: currentTenant }));
      setRefSummaryDataForTable([]);
      setRefDetailsDataForTable([]);
    }
  }, [currentTenant]);

  // Update strChannelFilters when tenant changes
  useEffect(() => {
    if (currentTenant) {
      setStrChannelFilters((prev) => ({ ...prev, administration: currentTenant }));
    }
  }, [currentTenant]);

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    t,
    chartAccounts,
    currentTenant,
    testMode,
    // Core state
    transactions,
    setTransactions,
    mutaties,
    loading,
    setLoading,
    message,
    setMessage,
    modalError,
    setModalError,
    lookupData,
    setLookupData,
    filterOptions,
    mutatiesFilters,
    setMutatiesFilters,
    // Check Accounts UI
    expandedRows,
    endDate,
    setEndDate,
    sequenceStartDate,
    setSequenceStartDate,
    openingBalanceDate,
    selectedAccount,
    setSelectedAccount,
    // Check Reference filters
    checkRefFilters,
    setCheckRefFilters,
    // Filterable tables
    refSummaryDataForTable,
    setRefSummaryDataForTable,
    refDetailsDataForTable,
    setRefDetailsDataForTable,
    refSummaryFilters,
    setRefSummaryFilter,
    handleRefSummarySort,
    refSummarySortField,
    refSummarySortDirection,
    processedRefSummary,
    refDetailsFilters,
    setRefDetailsFilter,
    handleRefDetailsSort,
    refDetailsSortField,
    refDetailsSortDirection,
    processedRefDetails,
    // STR Channel filters
    strChannelFilters,
    setStrChannelFilters,
    // Modal
    isOpen,
    onOpen,
    onClose,
    editingRecord,
    setEditingRecord,
    isInsertMode,
    // Handlers
    toggleRowExpansion,
    copyToClipboard,
    handleRef3Click,
    openEditModal,
    openInsertModal,
    // API
    fetchLookupData,
    fetchMutaties,
    fetchFilterOptions,
    mapLookupData,
  };
}
