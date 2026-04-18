import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Alert,
  AlertIcon,
  Button,
  Card,
  CardBody,
  HStack,
  Table,
  TableContainer,
  Tbody,
  Td,
  Thead,
  Tr,
  VStack
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';
import { formatCurrency, formatDate } from '../../utils/formatting';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { FilterableHeader } from '../filters/FilterableHeader';
import { YearFilter } from '../filters/YearFilter';

interface MutatiesRecord {
  TransactionDate: string;
  TransactionDescription: string;
  Amount: number;
  Reknum: string;
  AccountName: string;
  Administration: string;
  ReferenceNumber: string;
}

const INITIAL_FILTERS: Record<string, string> = {
  TransactionDate: '',
  TransactionDescription: '',
  Amount: '',
  Reknum: '',
  AccountName: '',
  Administration: '',
  ReferenceNumber: ''
};

const MutatiesReport: React.FC = () => {
  const { t, i18n } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();
  const [mutatiesData, setMutatiesData] = useState<MutatiesRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const isInitialMount = useRef(true);

  // Year selector — replaces the old start/end date inputs
  const currentYear = new Date().getFullYear().toString();
  const [selectedYear, setSelectedYear] = useState(currentYear);

  const availableYears = useMemo(() => {
    const now = new Date().getFullYear();
    return Array.from({ length: 6 }, (_, i) => (now - 5 + i).toString());
  }, []);

  // Derive dateFrom/dateTo from selected year
  const dateFrom = `${selectedYear}-01-01`;
  const dateTo = `${selectedYear}-12-31`;

  // Keep a ref so fetchMutatiesData reads latest values without
  // needing them in its dependency array.
  const filtersRef = useRef({ dateFrom, dateTo });
  filtersRef.current = { dateFrom, dateTo };

  const {
    filters,
    setFilter,
    resetFilters,
    handleSort,
    sortField,
    sortDirection,
    processedData
  } = useFilterableTable<MutatiesRecord>(mutatiesData, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'TransactionDate', direction: 'desc' },
  });

  const exportMutatiesCsv = useCallback(() => {
    const csvContent = [
      [t('tables.date'), t('tables.reference'), t('tables.description'), t('tables.amount'), t('tables.debit'), t('tables.credit'), t('filters.administration')],
      ...processedData.map(row => [
        row.TransactionDate,
        row.ReferenceNumber,
        row.TransactionDescription,
        row.Amount,
        row.Reknum,
        row.AccountName,
        row.Administration
      ])
    ].map(row => row.join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mutaties-${filtersRef.current.dateFrom}-${filtersRef.current.dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [processedData, t]);

  const fetchMutatiesData = useCallback(async () => {
    setLoading(true);
    try {
      if (!currentTenant) {
        console.error('No tenant selected for mutaties data fetch');
        return;
      }

      const current = filtersRef.current;
      const params = new URLSearchParams({
        dateFrom: current.dateFrom,
        dateTo: current.dateTo,
        administration: currentTenant || 'all',
        profitLoss: 'all'
      });

      const response = await authenticatedGet(buildEndpoint('/api/reports/mutaties-table', params));
      const data = await response.json();

      if (data.success) {
        setMutatiesData(data.data);
      } else {
        console.error('Failed to fetch mutaties data:', data.message || 'Unknown error');
      }
    } catch (err) {
      console.error('Error fetching mutaties data:', err);
    } finally {
      setLoading(false);
    }
  }, [currentTenant]);

  // Initial data fetch
  useEffect(() => {
    fetchMutatiesData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-fetch when year changes (skip initial mount — handled above)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    fetchMutatiesData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear]);

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      setMutatiesData([]);
      resetFilters();
      fetchMutatiesData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTenant]);

  // Tenant validation
  if (!currentTenant) {
    return (
      <Alert status="warning" data-testid="no-tenant-alert">
        <AlertIcon />
        {t('common:messages.noTenantSelected')}
      </Alert>
    );
  }

  const columnSortDirection = (field: string): 'asc' | 'desc' | null => {
    return sortField === field ? sortDirection : null;
  };

  const handleYearChange = (values: string[]) => {
    if (values.length > 0) {
      setSelectedYear(values[0]);
    }
  };

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={4} wrap="wrap" align="flex-end">
            <HStack maxW="200px">
              <YearFilter
                availableOptions={availableYears}
                values={[selectedYear]}
                onChange={handleYearChange}
                labelColor="white"
                bg="gray.600"
                color="white"
              />
            </HStack>
            <Button colorScheme="orange" onClick={fetchMutatiesData} isLoading={loading} size="sm">
              {t('actions.refreshReport')}
            </Button>
            <Button colorScheme="orange" onClick={exportMutatiesCsv} size="sm" data-testid="export-csv-button">
              {t('export.exportToCsv')}
            </Button>
          </HStack>
        </CardBody>
      </Card>

      <Card bg="gray.700">
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <FilterableHeader
                    label={t('tables.date')}
                    filterValue={filters.TransactionDate}
                    onFilterChange={(v) => setFilter('TransactionDate', v)}
                    sortable
                    sortDirection={columnSortDirection('TransactionDate')}
                    onSort={() => handleSort('TransactionDate')}
                  />
                  <FilterableHeader
                    label={t('tables.description')}
                    filterValue={filters.TransactionDescription}
                    onFilterChange={(v) => setFilter('TransactionDescription', v)}
                    sortable
                    sortDirection={columnSortDirection('TransactionDescription')}
                    onSort={() => handleSort('TransactionDescription')}
                  />
                  <FilterableHeader
                    label={t('tables.amount')}
                    filterValue={filters.Amount}
                    onFilterChange={(v) => setFilter('Amount', v)}
                    isNumeric
                    sortable
                    sortDirection={columnSortDirection('Amount')}
                    onSort={() => handleSort('Amount')}
                  />
                  <FilterableHeader
                    label={t('tables.account')}
                    filterValue={filters.AccountName}
                    onFilterChange={(v) => setFilter('AccountName', v)}
                    sortable
                    sortDirection={columnSortDirection('AccountName')}
                    onSort={() => handleSort('AccountName')}
                  />
                  <FilterableHeader
                    label={t('tables.reference')}
                    filterValue={filters.ReferenceNumber}
                    onFilterChange={(v) => setFilter('ReferenceNumber', v)}
                    sortable
                    sortDirection={columnSortDirection('ReferenceNumber')}
                    onSort={() => handleSort('ReferenceNumber')}
                  />
                </Tr>
              </Thead>
              <Tbody>
                {processedData.slice(0, 100).map((row, index) => (
                  <Tr key={index}>
                    <Td color="white" fontSize="sm">{formatDate(new Date(row.TransactionDate), i18n.language)}</Td>
                    <Td color="white" fontSize="sm" maxW="300px" isTruncated title={row.TransactionDescription}>{row.TransactionDescription}</Td>
                    <Td color="white" fontSize="sm" isNumeric>{formatCurrency(Number(row.Amount), i18n.language)}</Td>
                    <Td color="white" fontSize="sm">{row.AccountName}</Td>
                    <Td color="white" fontSize="sm">{row.ReferenceNumber}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>
    </VStack>
  );
};

export default MutatiesReport;
