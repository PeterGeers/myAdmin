/**
 * useTransactions Hook
 *
 * Standalone hook for the Transactions (Mutaties) page.
 * Encapsulates data fetching, filter state, modal state, and CRUD operations
 * for the mutaties table view.
 *
 * Extracted from useBankingState to allow TransactionsPage to be self-contained.
 *
 * @module hooks/useTransactions
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-2
 */

import { useCallback, useEffect, useState } from 'react';
import { useDisclosure, useToast } from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '@/services/apiService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import { useAccountLookup } from '@/hooks/useAccountLookup';
import { useTenant } from '@/context/TenantContext';
import type { Transaction } from '@/components/BankingProcessor.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FilterOptions {
  years: string[];
  administrations: string[];
}

export interface MutatiesFilters {
  years: string[];
}

export interface UseTransactionsReturn {
  // Data
  mutaties: Transaction[];
  filterOptions: FilterOptions;
  chartAccounts: ReturnType<typeof useAccountLookup>['accounts'];
  // Filters
  mutatiesFilters: MutatiesFilters;
  setMutatiesFilters: React.Dispatch<React.SetStateAction<MutatiesFilters>>;
  // Loading
  loading: boolean;
  // Modal
  isOpen: boolean;
  onClose: () => void;
  editingRecord: Transaction | null;
  setEditingRecord: React.Dispatch<React.SetStateAction<Transaction | null>>;
  isInsertMode: boolean;
  modalError: string;
  // Actions
  openEditModal: (record: Transaction) => void;
  openInsertModal: () => void;
  handleSaveRecord: () => Promise<void>;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  copyToClipboard: (text: string) => void;
  handleRef3Click: (ref3: string) => Promise<void>;
  // Refetch
  refetchMutaties: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTransactions(): UseTransactionsReturn {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const { accounts: chartAccounts } = useAccountLookup();
  const toast = useToast();

  // --- Data state ---
  const [mutaties, setMutaties] = useState<Transaction[]>([]);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    years: [],
    administrations: [],
  });
  const [mutatiesFilters, setMutatiesFilters] = useState<MutatiesFilters>({
    years: [new Date().getFullYear().toString()],
  });
  const [loading, setLoading] = useState(false);
  const [modalError, setModalError] = useState('');

  // --- Modal state ---
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [editingRecord, setEditingRecord] = useState<Transaction | null>(null);
  const [isInsertMode, setIsInsertMode] = useState(false);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------

  const fetchMutaties = useCallback(async () => {
    try {
      const tenant = localStorage.getItem('selectedTenant');
      if (!tenant) return;

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

  // Fetch data on mount and when filters change
  useEffect(() => {
    fetchFilterOptions();
    fetchMutaties();
  }, [fetchFilterOptions, fetchMutaties]);

  // Re-fetch when tenant changes
  useEffect(() => {
    if (currentTenant) {
      fetchMutaties();
    }
  }, [currentTenant, fetchMutaties]);

  // ---------------------------------------------------------------------------
  // Modal Handlers
  // ---------------------------------------------------------------------------

  const openEditModal = useCallback(
    (record: Transaction) => {
      setEditingRecord({ ...record });
      setIsInsertMode(false);
      setModalError('');
      onOpen();
    },
    [onOpen],
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
  // Save Record (insert or update)
  // ---------------------------------------------------------------------------

  const handleSaveRecord = useCallback(async () => {
    if (!editingRecord) return;
    try {
      setLoading(true);
      setModalError('');

      const endpoint = isInsertMode
        ? '/api/banking/insert-mutatie'
        : '/api/banking/update-mutatie';
      const successMsg = isInsertMode
        ? t('messages.recordInserted')
        : t('messages.recordUpdated');
      const errorMsg = isInsertMode
        ? t('messages.errorInserting')
        : t('messages.errorUpdating');

      const response = await authenticatedPost(endpoint, editingRecord);
      const data = await response.json();

      if (data.success) {
        toast({ title: successMsg, status: 'success', duration: 2000 });
        fetchMutaties();
        onClose();
      } else {
        setModalError(data.error || errorMsg);
      }
    } catch (error) {
      const errorMsg = isInsertMode
        ? t('messages.errorInserting')
        : t('messages.errorUpdating');
      setModalError(`${errorMsg}: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [editingRecord, isInsertMode, t, fetchMutaties, onClose, toast]);

  // ---------------------------------------------------------------------------
  // Keyboard Handler
  // ---------------------------------------------------------------------------

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
  // Utility Handlers
  // ---------------------------------------------------------------------------

  const copyToClipboard = useCallback(
    (text: string) => {
      navigator.clipboard.writeText(text).then(() => {
        toast({
          title: t('messages.copiedToClipboard'),
          status: 'info',
          duration: 2000,
          isClosable: true,
        });
      });
    },
    [t, toast],
  );

  const handleRef3Click = useCallback(
    async (ref3: string) => {
      if (ref3.startsWith('https://drive.goo')) {
        window.open(ref3, '_blank');
      } else if (ref3 && !ref3.startsWith('http')) {
        try {
          const resp = await authenticatedGet(
            `/api/storage/presigned-url?key=${encodeURIComponent(ref3)}`,
            { tenant: currentTenant || undefined },
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
    [currentTenant, copyToClipboard],
  );

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // Data
    mutaties,
    filterOptions,
    chartAccounts,
    // Filters
    mutatiesFilters,
    setMutatiesFilters,
    // Loading
    loading,
    // Modal
    isOpen,
    onClose,
    editingRecord,
    setEditingRecord,
    isInsertMode,
    modalError,
    // Actions
    openEditModal,
    openInsertModal,
    handleSaveRecord,
    handleKeyDown,
    copyToClipboard,
    handleRef3Click,
    // Refetch
    refetchMutaties: fetchMutaties,
  };
}
