/**
 * useStrChannelRevenue Hook
 *
 * Standalone hook for the STR Channel Revenue page.
 * Encapsulates data fetching, state management, and API calls for
 * previewing STR channel data, calculating revenue, and saving transactions.
 *
 * Extracted from useBankingState + useBankingUpload to allow
 * STRChannelRevenuePage to be self-contained.
 *
 * @module hooks/useStrChannelRevenue
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-4
 */

import { useCallback, useEffect, useState } from 'react';
import { useToast } from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '@/services/apiService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import { useTenant } from '@/context/TenantContext';
import { useTenantFunctions } from '@/hooks/useTenantFunctions';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StrChannelPreviewRow {
  ReferenceNumber?: string;
  Reknum?: string;
  transaction_count?: number;
  total_amount?: string | number;
  first_date?: string;
  last_date?: string;
  [key: string]: unknown;
}

export interface StrChannelTransaction {
  TransactionDate?: string;
  TransactionDescription?: string;
  TransactionAmount?: string | number;
  Debet?: string;
  Credit?: string;
  ReferenceNumber?: string;
  [key: string]: unknown;
}

export interface StrChannelSummary {
  ref1: string;
  month: number;
  year: number;
  end_date: string;
}

export interface StrChannelFilters {
  year: number;
  month: number;
  administration: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useStrChannelRevenue() {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const { hasFunction } = useTenantFunctions();
  const toast = useToast();

  // --- State ---
  const [strChannelPreview, setStrChannelPreview] = useState<StrChannelPreviewRow[]>([]);
  const [strChannelTransactions, setStrChannelTransactions] = useState<StrChannelTransaction[]>([]);
  const [strChannelSummary, setStrChannelSummary] = useState<StrChannelSummary | null>(null);
  const [strChannelFilters, setStrChannelFilters] = useState<StrChannelFilters>({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    administration: currentTenant || '',
  });
  const [loading, setLoading] = useState(false);
  const [testMode] = useState(false);

  // --- Visibility gate ---
  const isVisible = hasFunction('str_channel_revenue');

  // ---------------------------------------------------------------------------
  // API Calls
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
        toast({
          title: t('messages.foundStrChannels', {
            count: data.preview_data.length,
            month: strChannelFilters.month,
            year: strChannelFilters.year,
          }),
          status: 'success',
          duration: 3000,
        });
      } else {
        toast({
          title: t('messages.errorGeneric', { error: data.error }),
          status: 'error',
          duration: 4000,
        });
      }
    } catch (error) {
      toast({
        title: t('messages.errorFetchingPreview', { error: String(error) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setLoading(false);
    }
  }, [strChannelFilters, testMode, t, toast]);

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
        toast({
          title: t('messages.generatedTransactions', { count: data.transactions.length }),
          status: 'success',
          duration: 3000,
        });
      } else {
        toast({
          title: t('messages.errorGeneric', { error: data.error }),
          status: 'error',
          duration: 4000,
        });
      }
    } catch (error) {
      toast({
        title: t('messages.errorCalculating', { error: String(error) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setLoading(false);
    }
  }, [strChannelFilters, testMode, t, toast]);

  const saveStrChannelTransactions = useCallback(async () => {
    try {
      setLoading(true);

      const response = await authenticatedPost('/api/str-channel/save', {
        transactions: strChannelTransactions,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        toast({
          title: t('messages.transactionsSaved', { count: data.saved_count }),
          status: 'success',
          duration: 3000,
        });
        setStrChannelTransactions([]);
        setStrChannelSummary(null);
      } else {
        toast({
          title: t('messages.errorGeneric', { error: data.error }),
          status: 'error',
          duration: 4000,
        });
      }
    } catch (error) {
      toast({
        title: t('messages.errorSavingStrChannel', { error: String(error) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setLoading(false);
    }
  }, [strChannelTransactions, testMode, t, toast]);

  // ---------------------------------------------------------------------------
  // Handlers
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
  // Effects
  // ---------------------------------------------------------------------------

  // Update strChannelFilters when tenant changes
  useEffect(() => {
    if (currentTenant) {
      setStrChannelFilters((prev) => ({ ...prev, administration: currentTenant }));
      // Reset state on tenant change
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
    currentTenant,
    isVisible,
    loading,
    // STR Channel state
    strChannelFilters,
    setStrChannelFilters,
    strChannelPreview,
    strChannelTransactions,
    strChannelSummary,
    // Actions
    fetchStrChannelPreview,
    calculateStrChannelRevenue,
    saveStrChannelTransactions,
    handleKeyDown,
  };
}
