/**
 * useBankingState Hook
 *
 * Core shared state for the Banking Processor CSV import page:
 * transactions, lookup data, modal state, and tenant-sync effects.
 *
 * Note: Check Accounts, Check Reference, STR Channel, and Mutaties state
 * have been extracted to their own dedicated hooks (useCheckAccounts,
 * useCheckReference, useStrChannelRevenue, useTransactions).
 */

import { useCallback, useEffect, useState } from 'react';
import { useDisclosure } from '@chakra-ui/react';
import { authenticatedGet } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTypedTranslation } from './useTypedTranslation';
import { useAccountLookup } from './useAccountLookup';
import type { Transaction, LookupData, CreditCardAccount } from '../components/BankingProcessor.types';

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

/** Raw lookup data shape from the backend (before mapping) */
interface BankingLookupDataRaw {
  accounts: string[];
  descriptions: string[];
  bank_accounts: Array<{ rekeningNummer: string; Account: string; administration: string }>;
  credit_card_accounts: CreditCardAccountRaw[];
  exchange_rate_account: string | null;
  [key: string]: unknown;
}

/** Map backend credit_card_accounts fields to frontend interface */
export const mapLookupData = (data: BankingLookupDataRaw): LookupData => {
  const mappedCreditCards: CreditCardAccount[] = (data.credit_card_accounts || []).map((cc) => ({
    iban: cc.cc_bank_iban || cc.iban || '',
    Account: cc.Account || '',
    card_number: cc.card_number || '',
    administration: cc.administration || '',
  }));
  return {
    accounts: data.accounts,
    descriptions: data.descriptions,
    bank_accounts: data.bank_accounts,
    credit_card_accounts: mappedCreditCards,
    exchange_rate_account: data.exchange_rate_account,
  };
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

  // --- Modal state ---
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<Transaction | null>(null);
  const [isInsertMode, setIsInsertMode] = useState(false);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

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
  // API handlers — Lookup
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

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  useEffect(() => {
    fetchLookupData();
  }, [testMode, fetchLookupData]);

  // Auto-refresh when tenant changes
  useEffect(() => {
    if (currentTenant) {
      fetchLookupData();
    }
  }, [currentTenant, fetchLookupData]);

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
    loading,
    setLoading,
    message,
    setMessage,
    modalError,
    setModalError,
    lookupData,
    setLookupData,
    // Modal
    isOpen,
    onOpen,
    onClose,
    editingRecord,
    setEditingRecord,
    isInsertMode,
    // Handlers
    openEditModal,
    openInsertModal,
    // API
    fetchLookupData,
    mapLookupData,
  };
}
