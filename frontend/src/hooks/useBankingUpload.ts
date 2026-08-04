/**
 * useBankingUpload Hook
 *
 * Transaction upload, save, insert/update record operations,
 * and keyboard navigation for the Banking Processor CSV import page.
 *
 * Note: Check Accounts, Check Reference, and STR Channel operations
 * have been extracted to their own dedicated hooks (useCheckAccounts,
 * useCheckReference, useStrChannelRevenue).
 */

import { useCallback, useState } from 'react';
import { authenticatedPost } from '../services/apiService';
import type { Transaction } from '../components/BankingProcessor.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  /** Close modal */
  onClose: () => void;
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
    onClose,
  } = deps;

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
        onClose();
      } else {
        setModalError(data.error || t('messages.errorUpdating'));
      }
    } catch (error) {
      setModalError(t('messages.errorUpdating') + `: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [editingRecord, t, onClose, setLoading, setMessage, setModalError]);

  const insertRecord = useCallback(async () => {
    if (!editingRecord) return;
    try {
      setLoading(true);
      setModalError('');
      const response = await authenticatedPost('/api/banking/insert-mutatie', editingRecord);
      const data = await response.json();
      if (data.success) {
        setMessage(t('messages.recordInserted'));
        onClose();
      } else {
        setModalError(data.error || t('messages.errorInserting'));
      }
    } catch (error) {
      setModalError(t('messages.errorInserting') + `: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [editingRecord, t, onClose, setLoading, setMessage, setModalError]);

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

  // Handle ENTER key to move to next field
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

  return {
    // Save confirmation
    showSaveConfirmation,
    setShowSaveConfirmation,
    // Record CRUD
    handleSaveRecord,
    handleSaveTransactions,
    confirmSaveTransactions,
    updateTransaction,
    handleKeyDown,
  };
}
