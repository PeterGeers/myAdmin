/**
 * useBankingProcessor Hook
 *
 * Orchestrator that composes useBankingState, useBankingUpload, and
 * useBankingPatterns into a single API-compatible hook. Consumers
 * (BankingProcessor.tsx) don't need to change.
 */

import { useEffect } from 'react';
import { useBankingState, formatAmount, mapLookupData } from './useBankingState';
import { useBankingUpload } from './useBankingUpload';
import { useBankingPatterns } from './useBankingPatterns';
import type { PatternData } from './useBankingPatterns';

// Re-export types from the shared types file
export type { Transaction, CreditCardAccount, LookupData, BankingBalance } from '../components/BankingProcessor.types';
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
    fetchMutaties: state.fetchMutaties,
    onClose: state.onClose,
    endDate: state.endDate,
    selectedAccount: state.selectedAccount,
    sequenceStartDate: state.sequenceStartDate,
    checkRefFilters: state.checkRefFilters,
    strChannelFilters: state.strChannelFilters,
  });

  const patterns = useBankingPatterns({
    t: state.t,
    transactions: state.transactions,
    setTransactions: state.setTransactions,
    testMode: state.testMode,
    setLoading: state.setLoading,
    setMessage: state.setMessage,
  });

  // Sync upload's ref data into state's filterable table data sources
  useEffect(() => {
    state.setRefSummaryDataForTable(upload.refSummaryData);
  }, [upload.refSummaryData, state.setRefSummaryDataForTable]);

  useEffect(() => {
    state.setRefDetailsDataForTable(upload.selectedReferenceDetails);
  }, [upload.selectedReferenceDetails, state.setRefDetailsDataForTable]);

  // Fetch check ref options when filters change
  useEffect(() => {
    upload.fetchCheckRefOptions();
  }, [upload.fetchCheckRefOptions]);

  // Reset check state on tenant change
  useEffect(() => {
    if (state.currentTenant) {
      upload.resetCheckState();
      upload.resetRefState();
      upload.resetStrChannelState();
    }
  }, [state.currentTenant, upload.resetCheckState, upload.resetRefState, upload.resetStrChannelState]);

  // Merge patternResults — patterns hook owns the canonical value
  const patternResults = patterns.patternResults as PatternData | null;

  return {
    // From state
    t: state.t,
    chartAccounts: state.chartAccounts,
    transactions: state.transactions,
    setTransactions: state.setTransactions,
    mutaties: state.mutaties,
    loading: state.loading,
    setLoading: state.setLoading,
    message: state.message,
    setMessage: state.setMessage,
    patternResults,
    showSaveConfirmation: upload.showSaveConfirmation,
    setShowSaveConfirmation: upload.setShowSaveConfirmation,
    lookupData: state.lookupData,
    setLookupData: state.setLookupData,
    filterOptions: state.filterOptions,
    mutatiesFilters: state.mutatiesFilters,
    setMutatiesFilters: state.setMutatiesFilters,
    bankingBalances: upload.bankingBalances,
    checkingAccounts: upload.checkingAccounts,
    expandedRows: state.expandedRows,
    endDate: state.endDate,
    setEndDate: state.setEndDate,
    sequenceResult: upload.sequenceResult,
    checkingSequence: upload.checkingSequence,
    sequenceStartDate: state.sequenceStartDate,
    setSequenceStartDate: state.setSequenceStartDate,
    openingBalanceDate: state.openingBalanceDate,
    selectedAccount: state.selectedAccount,
    setSelectedAccount: state.setSelectedAccount,
    checkRefFilters: state.checkRefFilters,
    setCheckRefFilters: state.setCheckRefFilters,
    availableLedgers: upload.availableLedgers,
    refSummaryData: upload.refSummaryData,
    selectedReferenceDetails: upload.selectedReferenceDetails,
    selectedReference: upload.selectedReference,
    refSummaryFilters: state.refSummaryFilters,
    setRefSummaryFilter: state.setRefSummaryFilter,
    handleRefSummarySort: state.handleRefSummarySort,
    refSummarySortField: state.refSummarySortField,
    refSummarySortDirection: state.refSummarySortDirection,
    processedRefSummary: state.processedRefSummary,
    refDetailsFilters: state.refDetailsFilters,
    setRefDetailsFilter: state.setRefDetailsFilter,
    handleRefDetailsSort: state.handleRefDetailsSort,
    refDetailsSortField: state.refDetailsSortField,
    refDetailsSortDirection: state.refDetailsSortDirection,
    processedRefDetails: state.processedRefDetails,
    strChannelFilters: state.strChannelFilters,
    setStrChannelFilters: state.setStrChannelFilters,
    strChannelPreview: upload.strChannelPreview,
    strChannelTransactions: upload.strChannelTransactions,
    strChannelSummary: upload.strChannelSummary,
    patternSuggestions: patterns.patternSuggestions,
    showPatternApproval: patterns.showPatternApproval,
    setShowPatternApproval: patterns.setShowPatternApproval,
    isOpen: state.isOpen,
    onOpen: state.onOpen,
    onClose: state.onClose,
    editingRecord: state.editingRecord,
    setEditingRecord: state.setEditingRecord,
    isInsertMode: state.isInsertMode,
    modalError: state.modalError,
    toggleRowExpansion: state.toggleRowExpansion,
    copyToClipboard: state.copyToClipboard,
    handleRef3Click: state.handleRef3Click,
    openEditModal: state.openEditModal,
    openInsertModal: state.openInsertModal,
    handleSaveRecord: upload.handleSaveRecord,
    mapLookupData,
    fetchMutaties: state.fetchMutaties,
    checkBankingAccounts: upload.checkBankingAccounts,
    checkSequenceNumbers: upload.checkSequenceNumbers,
    fetchCheckRefData: upload.fetchCheckRefData,
    fetchReferenceDetails: upload.fetchReferenceDetails,
    fetchStrChannelPreview: upload.fetchStrChannelPreview,
    calculateStrChannelRevenue: upload.calculateStrChannelRevenue,
    saveStrChannelTransactions: upload.saveStrChannelTransactions,
    handleSaveTransactions: upload.handleSaveTransactions,
    confirmSaveTransactions: upload.confirmSaveTransactions,
    updateTransaction: upload.updateTransaction,
    handleKeyDown: upload.handleKeyDown,
    isPatternFilled: patterns.isPatternFilled,
    getPatternFieldStyle: patterns.getPatternFieldStyle,
    applyPatterns: patterns.applyPatterns,
    approvePatternSuggestions: patterns.approvePatternSuggestions,
    rejectPatternSuggestions: patterns.rejectPatternSuggestions,
    formatAmount,
    testMode: state.testMode,
    currentTenant: state.currentTenant,
  };
}
