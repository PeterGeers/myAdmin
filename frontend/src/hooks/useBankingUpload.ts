/**
 * useBankingUpload Hook
 *
 * Transaction upload, save, insert/update record operations,
 * keyboard navigation, check accounts/sequence, check references,
 * and STR channel revenue operations for the Banking Processor.
 */

import { useCallback, useState } from 'react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';
import type { Transaction, BankingBalance } from '../components/BankingProcessor.types';

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

export interface StrChannelSummary {
  ref1: string;
  month: number;
  year: number;
  end_date: string;
}

/** A row in the reference summary table. */
export interface RefSummaryRow {
  ReferenceNumber: string;
  transaction_count: number;
  total_amount: string | number;
  [key: string]: unknown;
}

/** A transaction row from reference details or STR channel. */
export interface TransactionRow {
  TransactionNumber?: string;
  TransactionDate?: string;
  TransactionDescription?: string;
  TransactionAmount?: string | number;
  Debet?: string;
  Credit?: string;
  ReferenceNumber?: string;
  [key: string]: unknown;
}

interface UseBankingUploadDeps {
  /** Translation function */
  t: (key: string, params?: Record<string, unknown>) => string;
  /** Current transactions state */
  transactions: Transaction[];
  /** Set transactions state */
  setTransactions: React.Dispatch<React.SetStateAction<Transaction[]>>;
  /** Test mode flag */
  testMode: boolean;
  /** Set loading state */
  setLoading: (loading: boolean) => void;
  /** Set message state */
  setMessage: (msg: string) => void;
  /** Set modal error */
  setModalError: (msg: string) => void;
  /** Editing record */
  editingRecord: Transaction | null;
  /** Is insert mode */
  isInsertMode: boolean;
  /** Fetch mutaties after record changes */
  fetchMutaties: () => Promise<void>;
  /** Close modal */
  onClose: () => void;
  /** End date for check accounts */
  endDate: string;
  /** Selected account for sequence check */
  selectedAccount: string;
  /** Sequence start date */
  sequenceStartDate: string;
  /** Check reference filters */
  checkRefFilters: { administration: string; ledger: string; referenceNumber: string };
  /** STR channel filters */
  strChannelFilters: { year: number; month: number; administration: string };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBankingUpload(deps: UseBankingUploadDeps) {
  const {
    t,
    transactions,
    setTransactions,
    testMode,
    setLoading,
    setMessage,
    setModalError,
    editingRecord,
    isInsertMode,
    fetchMutaties,
    onClose,
    endDate,
    selectedAccount,
    sequenceStartDate,
    checkRefFilters,
    strChannelFilters,
  } = deps;

  // --- Check Accounts state ---
  const [bankingBalances, setBankingBalances] = useState<BankingBalance[]>([]);
  const [checkingAccounts, setCheckingAccounts] = useState(false);
  const [sequenceResult, setSequenceResult] = useState<SequenceResult | null>(null);
  const [checkingSequence, setCheckingSequence] = useState(false);

  // --- Check Reference state ---
  const [availableLedgers, setAvailableLedgers] = useState<string[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [availableReferences, setAvailableReferences] = useState<string[]>([]);
  const [refSummaryData, setRefSummaryData] = useState<RefSummaryRow[]>([]);
  const [selectedReferenceDetails, setSelectedReferenceDetails] = useState<TransactionRow[]>([]);
  const [selectedReference, setSelectedReference] = useState<string>('');

  // --- STR Channel Revenue state ---
  const [strChannelPreview, setStrChannelPreview] = useState<TransactionRow[]>([]);
  const [strChannelTransactions, setStrChannelTransactions] = useState<TransactionRow[]>([]);
  const [strChannelSummary, setStrChannelSummary] = useState<StrChannelSummary | null>(null);

  // ---------------------------------------------------------------------------
  // Record CRUD
  // ---------------------------------------------------------------------------

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
  }, [editingRecord, t, fetchMutaties, onClose, setLoading, setMessage, setModalError]);

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
  }, [editingRecord, t, fetchMutaties, onClose, setLoading, setMessage, setModalError]);

  const handleSaveRecord = useCallback(() => {
    if (isInsertMode) {
      insertRecord();
    } else {
      updateRecord();
    }
  }, [isInsertMode, insertRecord, updateRecord]);

  // ---------------------------------------------------------------------------
  // Batch save transactions (two-step: show confirmation, then confirm)
  // ---------------------------------------------------------------------------

  const [showSaveConfirmation, setShowSaveConfirmation] = useState<boolean>(false);

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
      } else {
        setMessage(t('messages.errorGeneric', { error: data.error }));
      }
    } catch (error) {
      setMessage(t('messages.errorSaving', { error: String(error) }));
    } finally {
      setLoading(false);
    }
  }, [transactions, testMode, t, setLoading, setMessage, setTransactions]);

  // ---------------------------------------------------------------------------
  // Transaction editing
  // ---------------------------------------------------------------------------

  const updateTransaction = useCallback((rowId: number, field: keyof Transaction, value: string | number) => {
    setTransactions((prev) =>
      prev.map((tx) => (tx.row_id === rowId ? { ...tx, [field]: value } : tx))
    );
  }, [setTransactions]);

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

  // ---------------------------------------------------------------------------
  // Check Accounts & Sequence
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
  }, [testMode, endDate, t, setMessage]);

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
  }, [testMode, selectedAccount, sequenceStartDate, t, setMessage]);

  // ---------------------------------------------------------------------------
  // Check Reference
  // ---------------------------------------------------------------------------

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
        const filteredSummary = data.summary.filter((row: { total_amount?: string | number }) => {
          const amount = parseFloat(String(row.total_amount || 0));
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
  }, [checkRefFilters.ledger, checkRefFilters.administration, t, setLoading, setMessage]);

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

  // ---------------------------------------------------------------------------
  // STR Channel Revenue
  // ---------------------------------------------------------------------------

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
  }, [strChannelFilters, testMode, t, setLoading, setMessage]);

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
  }, [strChannelFilters, testMode, t, setLoading, setMessage]);

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
  }, [strChannelTransactions, testMode, t, setLoading, setMessage]);

  // ---------------------------------------------------------------------------
  // Reset helpers (called from effects in state hook)
  // ---------------------------------------------------------------------------

  const resetCheckState = useCallback(() => {
    setBankingBalances([]);
    setSequenceResult(null);
  }, []);

  const resetRefState = useCallback(() => {
    setRefSummaryData([]);
    setSelectedReferenceDetails([]);
  }, []);

  const resetStrChannelState = useCallback(() => {
    setStrChannelPreview([]);
    setStrChannelTransactions([]);
    setStrChannelSummary(null);
  }, []);

  return {
    // Save confirmation
    showSaveConfirmation,
    setShowSaveConfirmation,
    // Check Accounts
    bankingBalances,
    checkingAccounts,
    sequenceResult,
    checkingSequence,
    checkBankingAccounts,
    checkSequenceNumbers,
    // Check Reference
    availableLedgers,
    refSummaryData,
    selectedReferenceDetails,
    selectedReference,
    fetchCheckRefOptions,
    fetchCheckRefData,
    fetchReferenceDetails,
    // STR Channel
    strChannelPreview,
    strChannelTransactions,
    strChannelSummary,
    fetchStrChannelPreview,
    calculateStrChannelRevenue,
    saveStrChannelTransactions,
    // Record CRUD
    handleSaveRecord,
    handleSaveTransactions,
    confirmSaveTransactions,
    updateTransaction,
    handleKeyDown,
    // Reset helpers
    resetCheckState,
    resetRefState,
    resetStrChannelState,
  };
}
