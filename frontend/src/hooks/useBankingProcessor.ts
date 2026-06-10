/**
 * useBankingProcessor Hook
 *
 * Extracted from BankingProcessor.tsx — contains all shared state management,
 * API call handlers, business logic helpers, pattern matching logic, and
 * transaction CRUD operations for the Banking Processor page.
 */

import { useCallback, useEffect, useState } from 'react';
import { useDisclosure } from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTypedTranslation } from './useTypedTranslation';
import { useAccountLookup } from './useAccountLookup';
import { useFilterableTable } from './useFilterableTable';
import type { Transaction, LookupData, BankingBalance } from '../components/BankingProcessor.types';

// Re-export types from the shared types file
export type { Transaction, CreditCardAccount, LookupData, BankingBalance } from '../components/BankingProcessor.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SequenceResult {
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

interface StrChannelSummary {
  ref1: string;
  month: number;
  year: number;
  end_date: string;
}

interface PatternData {
  patterns_found: number;
  predictions_made: {
    debet: number;
    credit: number;
    reference: number;
  };
  confidence_scores: number[];
  average_confidence: number;
  enhanced_results: unknown;
}

// ---------------------------------------------------------------------------
// Utility: mapLookupData (stateless)
// ---------------------------------------------------------------------------

/** Map backend credit_card_accounts fields to frontend interface */
export const mapLookupData = (data: any): any => {
  if (data.credit_card_accounts) {
    data.credit_card_accounts = data.credit_card_accounts.map((cc: any) => ({
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

export function useBankingProcessor() {
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
  const [patternResults, setPatternResults] = useState<PatternData | null>(null);
  const [showSaveConfirmation, setShowSaveConfirmation] = useState<boolean>(false);
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

  // --- Check Accounts state ---
  const [bankingBalances, setBankingBalances] = useState<BankingBalance[]>([]);
  const [checkingAccounts, setCheckingAccounts] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [endDate, setEndDate] = useState('');
  const [sequenceResult, setSequenceResult] = useState<SequenceResult | null>(null);
  const [checkingSequence, setCheckingSequence] = useState(false);
  const [sequenceStartDate, setSequenceStartDate] = useState('2025-01-01');
  const [openingBalanceDate, setOpeningBalanceDate] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState('');

  // --- Check Reference state ---
  const [checkRefFilters, setCheckRefFilters] = useState({
    administration: currentTenant || 'GoodwinSolutions',
    ledger: 'all',
    referenceNumber: 'all',
  });
  const [availableLedgers, setAvailableLedgers] = useState<string[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [availableReferences, setAvailableReferences] = useState<string[]>([]);
  const [refSummaryData, setRefSummaryData] = useState<any[]>([]);
  const [selectedReferenceDetails, setSelectedReferenceDetails] = useState<any[]>([]);
  const [selectedReference, setSelectedReference] = useState<string>('');

  // Check Reference - filterable table hooks
  const REF_SUMMARY_FILTERS: Record<string, string> = { ReferenceNumber: '', transaction_count: '', total_amount: '' };
  const REF_DETAILS_FILTERS: Record<string, string> = { TransactionNumber: '', TransactionDate: '', Amount: '', TransactionDescription: '' };

  const {
    filters: refSummaryFilters,
    setFilter: setRefSummaryFilter,
    handleSort: handleRefSummarySort,
    sortField: refSummarySortField,
    sortDirection: refSummarySortDirection,
    processedData: processedRefSummary,
  } = useFilterableTable(refSummaryData, {
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
  } = useFilterableTable(selectedReferenceDetails, {
    initialFilters: REF_DETAILS_FILTERS,
    defaultSort: { field: 'TransactionDate', direction: 'desc' },
  });

  // --- STR Channel Revenue state ---
  const [strChannelFilters, setStrChannelFilters] = useState({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    administration: currentTenant || 'GoodwinSolutions',
  });
  const [strChannelPreview, setStrChannelPreview] = useState<any[]>([]);
  const [strChannelTransactions, setStrChannelTransactions] = useState<any[]>([]);
  const [strChannelSummary, setStrChannelSummary] = useState<StrChannelSummary | null>(null);

  // --- Pattern suggestion state ---
  const [patternSuggestions, setPatternSuggestions] = useState<PatternData | null>(null);
  const [showPatternApproval, setShowPatternApproval] = useState(false);
  const [originalTransactions, setOriginalTransactions] = useState<Transaction[]>([]);

  // --- Modal state ---
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<Transaction | null>(null);
  const [isInsertMode, setIsInsertMode] = useState(false);

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
  // API handlers
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
      const params = new URLSearchParams({
        years: mutatiesFilters.years.join(','),
        administration: tenant || 'all',
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

  const updateRecord = useCallback(async () => {
    if (!editingRecord) return;
    try {
      setLoading(true);
      setModalError('');
      const response = await authenticatedPost('/api/banking/update-mutatie', editingRecord);
      const data = await response.json();
      if (data.success) {
        setMessage(t('messages.recordUpdated'));
        fetchMutaties();
        onClose();
      } else {
        setModalError(data.error || t('messages.errorUpdating'));
      }
    } catch (error) {
      setModalError(t('messages.errorUpdating') + `: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [editingRecord, t, fetchMutaties, onClose]);

  const insertRecord = useCallback(async () => {
    if (!editingRecord) return;
    try {
      setLoading(true);
      setModalError('');
      const response = await authenticatedPost('/api/banking/insert-mutatie', editingRecord);
      const data = await response.json();
      if (data.success) {
        setMessage(t('messages.recordInserted'));
        fetchMutaties();
        onClose();
      } else {
        setModalError(data.error || t('messages.errorInserting'));
      }
    } catch (error) {
      setModalError(t('messages.errorInserting') + `: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [editingRecord, t, fetchMutaties, onClose]);

  const handleSaveRecord = useCallback(() => {
    if (isInsertMode) {
      insertRecord();
    } else {
      updateRecord();
    }
  }, [isInsertMode, insertRecord, updateRecord]);

  const checkBankingAccounts = useCallback(async () => {
    try {
      setCheckingAccounts(true);
      const params = new URLSearchParams({ test_mode: testMode.toString() });
      if (endDate) params.append('end_date', endDate);

      const response = await authenticatedGet(`/api/banking/check-accounts?${params}`);
      const data = await response.json();

      if (data.success) {
        setBankingBalances(data.balances);
        setMessage(
          endDate
            ? t('messages.foundAccountsAsOf', { count: data.count, date: endDate })
            : t('messages.foundAccounts', { count: data.count })
        );
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorCheckingAccounts', { error: String(error) }));
    } finally {
      setCheckingAccounts(false);
    }
  }, [testMode, endDate, t]);

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
        setMessage(
          t('messages.sequenceCheckComplete', { account: account_code, administration }) + ` - ${gapMsg}`
        );
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorCheckingSequence', { error: String(error) }));
    } finally {
      setCheckingSequence(false);
    }
  }, [testMode, selectedAccount, sequenceStartDate, t]);

  const fetchCheckRefOptions = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        administration: checkRefFilters.administration,
        ledger: checkRefFilters.ledger,
      });
      const response = await authenticatedGet(`/api/reports/filter-options?${params}`);
      const data = await response.json();
      if (data.success) {
        setAvailableLedgers(data.ledgers || []);
        setAvailableReferences(data.references || []);
      }
    } catch (err) {
      console.error('Error fetching filter options:', err);
    }
  }, [checkRefFilters.administration, checkRefFilters.ledger]);

  const fetchCheckRefData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        referenceNumber: 'all',
        ledger: checkRefFilters.ledger,
        administration: checkRefFilters.administration,
      });

      const response = await authenticatedGet(`/api/reports/check-reference?${params}`);
      const data = await response.json();

      if (data.success) {
        const filteredSummary = data.summary.filter((row: any) => {
          const amount = parseFloat(row.total_amount || 0);
          return Math.abs(amount) > 0.01;
        });
        setRefSummaryData(filteredSummary);
        setMessage(t('messages.foundReferences', { count: filteredSummary.length }));
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (err) {
      console.error('Error fetching check reference data:', err);
      setMessage(t('messages.errorFetchingData', { error: err }));
    } finally {
      setLoading(false);
    }
  }, [checkRefFilters.ledger, checkRefFilters.administration, t]);

  const fetchReferenceDetails = useCallback(
    async (referenceNumber: string) => {
      try {
        const params = new URLSearchParams({
          referenceNumber: referenceNumber,
          ledger: checkRefFilters.ledger,
          administration: checkRefFilters.administration,
        });

        const response = await authenticatedGet(`/api/reports/check-reference?${params}`);
        const data = await response.json();

        if (data.success) {
          setSelectedReferenceDetails(data.transactions);
          setSelectedReference(referenceNumber);
        }
      } catch (err) {
        console.error('Error fetching reference details:', err);
      }
    },
    [checkRefFilters.ledger, checkRefFilters.administration]
  );

  // --- STR Channel Revenue functions ---

  const fetchStrChannelPreview = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        year: strChannelFilters.year.toString(),
        month: strChannelFilters.month.toString(),
        administration: strChannelFilters.administration,
        test_mode: testMode.toString(),
      });

      const response = await authenticatedGet(`/api/str-channel/preview?${params}`);
      const data = await response.json();

      if (data.success) {
        setStrChannelPreview(data.preview_data);
        setMessage(
          t('messages.foundStrChannels', {
            count: data.preview_data.length,
            month: strChannelFilters.month,
            year: strChannelFilters.year,
          })
        );
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorFetchingPreview', { error: String(error) }));
    } finally {
      setLoading(false);
    }
  }, [strChannelFilters, testMode, t]);

  const calculateStrChannelRevenue = useCallback(async () => {
    try {
      setLoading(true);

      const response = await authenticatedPost('/api/str-channel/calculate', {
        year: strChannelFilters.year,
        month: strChannelFilters.month,
        administration: strChannelFilters.administration,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        setStrChannelTransactions(data.transactions);
        setStrChannelSummary(data.summary);
        setMessage(t('messages.generatedTransactions', { count: data.transactions.length }));
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorCalculating', { error }));
    } finally {
      setLoading(false);
    }
  }, [strChannelFilters, testMode, t]);

  const saveStrChannelTransactions = useCallback(async () => {
    try {
      setLoading(true);

      const response = await authenticatedPost('/api/str-channel/save', {
        transactions: strChannelTransactions,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        setMessage(t('messages.transactionsSaved', { count: data.saved_count }));
        setStrChannelTransactions([]);
        setStrChannelSummary(null);
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorSavingStrChannel', { error }));
    } finally {
      setLoading(false);
    }
  }, [strChannelTransactions, testMode, t]);

  // --- Transaction handlers ---

  const handleSaveTransactions = useCallback(() => {
    setShowSaveConfirmation(true);
  }, []);

  const confirmSaveTransactions = useCallback(async () => {
    try {
      setLoading(true);
      setShowSaveConfirmation(false);

      const response = await authenticatedPost('/api/banking/save-transactions', {
        transactions: transactions,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        setMessage(t('messages.transactionsSavedSuccess', { count: data.saved_count, table: data.table }));
        setTransactions([]);
        setPatternResults(null);
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorSaving', { error: String(error) }));
    } finally {
      setLoading(false);
    }
  }, [transactions, testMode, t]);

  const updateTransaction = useCallback((rowId: number, field: keyof Transaction, value: string | number) => {
    setTransactions((prev) =>
      prev.map((tx) => (tx.row_id === rowId ? { ...tx, [field]: value } : tx))
    );
  }, []);

  // REQ-UI-001 & REQ-UI-002: Handle ENTER key to move to next field
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const form = e.currentTarget.closest('form');
      if (form) {
        const inputs = Array.from(form.querySelectorAll('input, select, textarea')) as HTMLElement[];
        const currentIndex = inputs.indexOf(e.currentTarget as HTMLElement);
        const nextInput = inputs[currentIndex + 1];
        if (nextInput) {
          nextInput.focus();
        }
      }
    }
  }, []);

  // REQ-UI-008: Helper to check if field was auto-filled by patterns
  const isPatternFilled = useCallback(
    (transaction: Transaction, field: string) => {
      const originalTx = originalTransactions.find((tx) => tx.row_id === transaction.row_id);
      if (!originalTx) return false;

      const fieldKey =
        field === 'debet' ? 'Debet' : field === 'credit' ? 'Credit' : field === 'reference' ? 'ReferenceNumber' : field;

      const originalValue = originalTx[fieldKey as keyof Transaction] || '';
      const currentValue = transaction[fieldKey as keyof Transaction] || '';

      return !originalValue && !!currentValue && !!patternSuggestions;
    },
    [originalTransactions, patternSuggestions]
  );

  // REQ-UI-008: Get styling for pattern-filled fields
  const getPatternFieldStyle = useCallback(
    (transaction: Transaction, field: string) => {
      if (isPatternFilled(transaction, field)) {
        return {
          bg: 'blue.50',
          borderColor: 'blue.300',
          borderWidth: '2px',
          _hover: { bg: 'blue.100' },
        };
      }
      return {};
    },
    [isPatternFilled]
  );

  // --- Pattern logic ---

  const applyPatterns = useCallback(async () => {
    try {
      setLoading(true);
      setPatternResults(null);

      // Store original transactions before applying suggestions
      setOriginalTransactions([...transactions]);

      const response = await authenticatedPost('/api/banking/apply-patterns', {
        transactions: transactions,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        setTransactions(data.transactions);

        const results = data.enhanced_results || data;

        const patternData: PatternData = {
          patterns_found: data.patterns_found || results.total_transactions || 0,
          predictions_made: results.predictions_made || { debet: 0, credit: 0, reference: 0 },
          confidence_scores: results.confidence_scores || [],
          average_confidence: results.average_confidence || 0,
          enhanced_results: data.enhanced_results,
        };

        setPatternResults(patternData);
        setPatternSuggestions(patternData);

        const totalPredictions = Object.values(patternData.predictions_made).reduce(
          (a: number, b: unknown) => a + (typeof b === 'number' ? b : 0),
          0
        );

        if (totalPredictions > 0) {
          setShowPatternApproval(true);
          setMessage(t('messages.patternSuggestionsFound', { count: totalPredictions }));
        } else {
          setMessage(t('messages.noPatternSuggestions'));
        }
      } else {
        setMessage(t('messages.errorApplyingPatterns', { error: data.error }));
        setPatternResults(null);
      }
    } catch (error) {
      setMessage(t('messages.errorApplyingPatterns', { error: String(error) }));
      setPatternResults(null);
    } finally {
      setLoading(false);
    }
  }, [transactions, testMode, t]);

  const approvePatternSuggestions = useCallback(() => {
    setShowPatternApproval(false);
    const count = Object.values(patternSuggestions?.predictions_made || {}).reduce(
      (a: number, b: unknown) => a + (typeof b === 'number' ? b : 0),
      0
    );
    setMessage(t('messages.patternSuggestionsApproved', { count }));
  }, [patternSuggestions, t]);

  const rejectPatternSuggestions = useCallback(() => {
    setTransactions([...originalTransactions]);
    setPatternResults(null);
    setPatternSuggestions(null);
    setShowPatternApproval(false);
    setMessage(t('messages.patternSuggestionsRejected'));
  }, [originalTransactions, t]);

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
      setBankingBalances([]);
      setSelectedAccount('');
      setSequenceResult(null);
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

  // Fetch check ref options when filters change
  useEffect(() => {
    fetchCheckRefOptions();
  }, [fetchCheckRefOptions]);

  // Update checkRefFilters when tenant changes
  useEffect(() => {
    if (currentTenant) {
      setCheckRefFilters((prev) => ({ ...prev, administration: currentTenant }));
      setRefSummaryData([]);
      setSelectedReferenceDetails([]);
    }
  }, [currentTenant]);

  // Update strChannelFilters when tenant changes
  useEffect(() => {
    if (currentTenant) {
      setStrChannelFilters((prev) => ({ ...prev, administration: currentTenant }));
      setStrChannelPreview([]);
      setStrChannelTransactions([]);
      setStrChannelSummary(null);
    }
  }, [currentTenant]);

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    t,
    chartAccounts,
    transactions,
    setTransactions,
    mutaties,
    loading,
    setLoading,
    message,
    setMessage,
    patternResults,
    showSaveConfirmation,
    setShowSaveConfirmation,
    lookupData,
    setLookupData,
    filterOptions,
    mutatiesFilters,
    setMutatiesFilters,
    bankingBalances,
    checkingAccounts,
    expandedRows,
    endDate,
    setEndDate,
    sequenceResult,
    checkingSequence,
    sequenceStartDate,
    setSequenceStartDate,
    openingBalanceDate,
    selectedAccount,
    setSelectedAccount,
    checkRefFilters,
    setCheckRefFilters,
    availableLedgers,
    refSummaryData,
    selectedReferenceDetails,
    selectedReference,
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
    strChannelFilters,
    setStrChannelFilters,
    strChannelPreview,
    strChannelTransactions,
    strChannelSummary,
    patternSuggestions,
    showPatternApproval,
    setShowPatternApproval,
    isOpen,
    onOpen,
    onClose,
    editingRecord,
    setEditingRecord,
    isInsertMode,
    modalError,
    toggleRowExpansion,
    copyToClipboard,
    handleRef3Click,
    openEditModal,
    openInsertModal,
    handleSaveRecord,
    mapLookupData,
    fetchMutaties,
    checkBankingAccounts,
    checkSequenceNumbers,
    fetchCheckRefData,
    fetchReferenceDetails,
    fetchStrChannelPreview,
    calculateStrChannelRevenue,
    saveStrChannelTransactions,
    handleSaveTransactions,
    confirmSaveTransactions,
    updateTransaction,
    handleKeyDown,
    isPatternFilled,
    getPatternFieldStyle,
    applyPatterns,
    approvePatternSuggestions,
    rejectPatternSuggestions,
    formatAmount,
    testMode,
    currentTenant,
  };
}
