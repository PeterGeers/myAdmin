/**
 * BankingProcessor Component
 *
 * Single-purpose CSV import page:
 * - Upload CSV bank statement
 * - Pattern matching for automatic account assignment
 * - Review & save transactions
 */

import { Box } from '@chakra-ui/react';
import React from 'react';
import BankingProcessorTable from './BankingProcessorTable';
import BankingFileUpload from './BankingFileUpload';
import BankingPatternPanel from './BankingPatternPanel';
import BankingTransactionModal from './BankingTransactionModal';
import { useBankingProcessor } from '../hooks/useBankingProcessor';

// Re-export types and utilities for backward compatibility
export type { Transaction, CreditCardAccount, LookupData } from './BankingProcessor.types';
export { parseCSVRow, processRevolutTransaction, processRabobankTransaction } from './BankingProcessor.utils';

const BankingProcessor: React.FC = () => {
  const bp = useBankingProcessor();

  return (
    <Box w="100%" p={4}>
      {/* CSV File Upload */}
      <BankingFileUpload
        lookupData={bp.lookupData}
        setLookupData={bp.setLookupData}
        testMode={bp.testMode}
        onTransactionsLoaded={bp.setTransactions}
        setLoading={bp.setLoading}
        loading={bp.loading}
        message={bp.message}
        setMessage={bp.setMessage}
        mapLookupData={bp.mapLookupData}
      />

      {/* Transaction Table with Pattern Results */}
      <BankingProcessorTable
        transactions={bp.transactions}
        chartAccounts={bp.chartAccounts}
        loading={bp.loading}
        patternResults={bp.patternResults}
        updateTransaction={bp.updateTransaction}
        onApplyPatterns={bp.applyPatterns}
        onSaveTransactions={bp.handleSaveTransactions}
        getPatternFieldStyle={bp.getPatternFieldStyle}
        t={bp.t}
      />

      {/* Edit/Insert Record Modal */}
      <BankingTransactionModal
        isOpen={bp.isOpen}
        onClose={bp.onClose}
        editingRecord={bp.editingRecord}
        setEditingRecord={bp.setEditingRecord}
        isInsertMode={bp.isInsertMode}
        loading={bp.loading}
        modalError={bp.modalError}
        chartAccounts={bp.chartAccounts}
        onSave={bp.handleSaveRecord}
        onKeyDown={bp.handleKeyDown}
        t={bp.t}
      />

      {/* Pattern Matching Panel */}
      <BankingPatternPanel
        transactions={bp.transactions}
        loading={bp.loading}
        patternResults={bp.patternResults}
        patternSuggestions={bp.patternSuggestions}
        showPatternApproval={bp.showPatternApproval}
        showSaveConfirmation={bp.showSaveConfirmation}
        onApprovePatterns={bp.approvePatternSuggestions}
        onRejectPatterns={bp.rejectPatternSuggestions}
        onClosePatternApproval={() => bp.setShowPatternApproval(false)}
        onConfirmSave={bp.confirmSaveTransactions}
        onCloseSaveConfirmation={() => bp.setShowSaveConfirmation(false)}
        t={bp.t}
      />
    </Box>
  );
};

export default BankingProcessor;
