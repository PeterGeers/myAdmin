/**
 * useBankingProcessor Hook
 *
 * Orchestrator that composes useBankingState, useBankingUpload, and
 * useBankingPatterns into a single API for the CSV import page.
 *
 * Note: Tab-specific state (mutaties, check accounts, check reference,
 * STR channel revenue) has been removed — those features now live in
 * their own standalone pages with dedicated hooks.
 */

import { useBankingState, formatAmount, mapLookupData } from './useBankingState';
import { useBankingUpload } from './useBankingUpload';
import { useBankingPatterns } from './useBankingPatterns';
import type { PatternData } from './useBankingPatterns';

// Re-export types from the shared types file
export type { Transaction, CreditCardAccount, LookupData } from '../components/BankingProcessor.types';
export type { PatternData } from './useBankingPatterns';
export { formatAmount, mapLookupData } from './useBankingState';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBankingProcessor() {
  const state = useBankingState();

  const upload = useBankingUpload({
    t: state.t,
    transactions: state.transactions,
    setTransactions: state.setTransactions,
    testMode: state.testMode,
    setLoading: state.setLoading,
    setMessage: state.setMessage,
    setModalError: state.setModalError,
    editingRecord: state.editingRecord,
    isInsertMode: state.isInsertMode,
    onClose: state.onClose,
  });

  const patterns = useBankingPatterns({
    t: state.t,
    transactions: state.transactions,
    setTransactions: state.setTransactions,
    testMode: state.testMode,
    setLoading: state.setLoading,
    setMessage: state.setMessage,
  });

  // Merge patternResults — patterns hook owns the canonical value
  const patternResults = patterns.patternResults as PatternData | null;

  return {
    // From state
    t: state.t,
    chartAccounts: state.chartAccounts,
    transactions: state.transactions,
    setTransactions: state.setTransactions,
    loading: state.loading,
    setLoading: state.setLoading,
    message: state.message,
    setMessage: state.setMessage,
    lookupData: state.lookupData,
    setLookupData: state.setLookupData,
    testMode: state.testMode,
    // Modal
    isOpen: state.isOpen,
    onClose: state.onClose,
    editingRecord: state.editingRecord,
    setEditingRecord: state.setEditingRecord,
    isInsertMode: state.isInsertMode,
    modalError: state.modalError,
    // From upload
    showSaveConfirmation: upload.showSaveConfirmation,
    setShowSaveConfirmation: upload.setShowSaveConfirmation,
    handleSaveTransactions: upload.handleSaveTransactions,
    confirmSaveTransactions: upload.confirmSaveTransactions,
    updateTransaction: upload.updateTransaction,
    handleKeyDown: upload.handleKeyDown,
    handleSaveRecord: upload.handleSaveRecord,
    // From patterns
    patternResults,
    patternSuggestions: patterns.patternSuggestions,
    showPatternApproval: patterns.showPatternApproval,
    setShowPatternApproval: patterns.setShowPatternApproval,
    applyPatterns: patterns.applyPatterns,
    approvePatternSuggestions: patterns.approvePatternSuggestions,
    rejectPatternSuggestions: patterns.rejectPatternSuggestions,
    getPatternFieldStyle: patterns.getPatternFieldStyle,
    // Utility
    mapLookupData,
    formatAmount,
  };
}
