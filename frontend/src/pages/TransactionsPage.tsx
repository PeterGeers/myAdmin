/**
 * TransactionsPage — Standalone page for the Mutaties (Transactions) table.
 *
 * Extracted from BankingProcessor to be accessible directly from the FIN menu.
 * Uses the useTransactions hook for all data fetching, state, and handlers.
 *
 * @module pages/TransactionsPage
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-2
 */

import React from 'react';
import { Box } from '@chakra-ui/react';
import BankingMutatiesTab from '@/components/banking/BankingMutatiesTab';
import BankingTransactionModal from '@/components/BankingTransactionModal';
import { useTransactions } from '@/hooks/useTransactions';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TransactionsPage: React.FC = () => {
  const { t } = useTypedTranslation('banking');
  const {
    mutaties,
    filterOptions,
    chartAccounts,
    mutatiesFilters,
    setMutatiesFilters,
    loading,
    isOpen,
    onClose,
    editingRecord,
    setEditingRecord,
    isInsertMode,
    modalError,
    openEditModal,
    openInsertModal,
    handleSaveRecord,
    handleKeyDown,
    copyToClipboard,
    handleRef3Click,
  } = useTransactions();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box w="100%" p={4}>
      <BankingMutatiesTab
        mutaties={mutaties}
        filterOptions={filterOptions}
        mutatiesFilters={mutatiesFilters}
        setMutatiesFilters={setMutatiesFilters}
        openEditModal={openEditModal}
        openInsertModal={openInsertModal}
        copyToClipboard={copyToClipboard}
        handleRef3Click={handleRef3Click}
      />

      <BankingTransactionModal
        isOpen={isOpen}
        onClose={onClose}
        editingRecord={editingRecord}
        setEditingRecord={setEditingRecord}
        isInsertMode={isInsertMode}
        loading={loading}
        modalError={modalError}
        chartAccounts={chartAccounts}
        onSave={handleSaveRecord}
        onKeyDown={handleKeyDown}
        t={t}
      />
    </Box>
  );
};

export default TransactionsPage;
