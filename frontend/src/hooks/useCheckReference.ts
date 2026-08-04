/**
 * useCheckReference Hook
 *
 * Standalone hook for the Check Reference page.
 * Encapsulates data fetching, state management, and API calls for
 * checking reference numbers across ledgers.
 *
 * Extracted from useBankingState + useBankingUpload to allow
 * CheckReferencePage to be self-contained.
 *
 * @module hooks/useCheckReference
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-3
 */

import { useCallback, useEffect, useState } from 'react';
import { useToast } from '@chakra-ui/react';
import { authenticatedGet } from '@/services/apiService';
import { useTypedTranslation } from '@/hooks/useTypedTranslation';
import { useFilterableTable } from '@/hooks/useFilterableTable';
import { useTenant } from '@/context/TenantContext';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RefSummaryRow {
  ReferenceNumber: string;
  transaction_count: number;
  total_amount: string | number;
  [key: string]: unknown;
}

export interface TransactionRow {
  TransactionNumber?: string;
  TransactionDate?: string;
  TransactionDescription?: string;
  Amount?: string | number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCheckReference() {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const toast = useToast();

  // --- Filter state ---
  const [checkRefFilters, setCheckRefFilters] = useState({
    administration: currentTenant || 'GoodwinSolutions',
    ledger: 'all',
    referenceNumber: 'all',
  });

  // --- Data state ---
  const [availableLedgers, setAvailableLedgers] = useState<string[]>([]);
  const [availableReferences, setAvailableReferences] = useState<string[]>([]);
  const [refSummaryData, setRefSummaryData] = useState<RefSummaryRow[]>([]);
  const [selectedReferenceDetails, setSelectedReferenceDetails] = useState<TransactionRow[]>([]);
  const [selectedReference, setSelectedReference] = useState<string>('');
  const [loading, setLoading] = useState(false);

  // --- Filterable table hooks for summary ---
  const REF_SUMMARY_FILTERS: Record<string, string> = {
    ReferenceNumber: '',
    transaction_count: '',
    total_amount: '',
  };

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

  // --- Filterable table hooks for details ---
  const REF_DETAILS_FILTERS: Record<string, string> = {
    TransactionNumber: '',
    TransactionDate: '',
    Amount: '',
    TransactionDescription: '',
  };

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

  // ---------------------------------------------------------------------------
  // API Calls
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
        const filteredSummary = data.summary.filter(
          (row: { total_amount?: string | number }) => {
            const amount = parseFloat(String(row.total_amount || 0));
            return Math.abs(amount) > 0.01;
          },
        );
        setRefSummaryData(filteredSummary);
        setSelectedReferenceDetails([]);
        setSelectedReference('');
        toast({
          title: t('messages.foundReferences', { count: filteredSummary.length }),
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
    } catch (err) {
      console.error('Error fetching check reference data:', err);
      toast({
        title: t('messages.errorFetchingData', { error: String(err) }),
        status: 'error',
        duration: 4000,
      });
    } finally {
      setLoading(false);
    }
  }, [checkRefFilters.ledger, checkRefFilters.administration, t, toast]);

  const fetchReferenceDetails = useCallback(
    async (referenceNumber: string) => {
      try {
        const params = new URLSearchParams({
          referenceNumber,
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
    [checkRefFilters.ledger, checkRefFilters.administration],
  );

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Fetch filter options when administration/ledger changes
  useEffect(() => {
    fetchCheckRefOptions();
  }, [fetchCheckRefOptions]);

  // Reset state on tenant change
  useEffect(() => {
    if (currentTenant) {
      setCheckRefFilters((prev) => ({ ...prev, administration: currentTenant }));
      setRefSummaryData([]);
      setSelectedReferenceDetails([]);
      setSelectedReference('');
    }
  }, [currentTenant]);

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    t,
    loading,
    currentTenant,
    // Filters
    checkRefFilters,
    setCheckRefFilters,
    availableLedgers,
    availableReferences,
    // Summary data
    refSummaryData,
    refSummaryFilters,
    setRefSummaryFilter,
    handleRefSummarySort,
    refSummarySortField,
    refSummarySortDirection,
    processedRefSummary,
    // Detail data
    selectedReference,
    selectedReferenceDetails,
    refDetailsFilters,
    setRefDetailsFilter,
    handleRefDetailsSort,
    refDetailsSortField,
    refDetailsSortDirection,
    processedRefDetails,
    // Actions
    fetchCheckRefData,
    fetchReferenceDetails,
  };
}
