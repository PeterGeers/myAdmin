/**
 * BudgetLineTable — Sortable/filterable table showing budget lines.
 *
 * Displays account code, period mode, dimension, and total with
 * FilterableHeader columns for inline filtering and sorting.
 */

import React from 'react';
import {
  Box, Flex, Spinner, Text,
  Table, Thead, Tbody, Tr, Td,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { FilterableHeader } from '../filters/FilterableHeader';
import { BudgetLineTableProps } from './types';
import { BudgetLine } from '../../types/budget';

/** Compute total from a BudgetLine's 12 monthly amounts */
export const lineTotal = (line: BudgetLine): number =>
  (Number(line.month_01) || 0) + (Number(line.month_02) || 0) +
  (Number(line.month_03) || 0) + (Number(line.month_04) || 0) +
  (Number(line.month_05) || 0) + (Number(line.month_06) || 0) +
  (Number(line.month_07) || 0) + (Number(line.month_08) || 0) +
  (Number(line.month_09) || 0) + (Number(line.month_10) || 0) +
  (Number(line.month_11) || 0) + (Number(line.month_12) || 0);

/** Format dimension display */
export const formatDimension = (line: BudgetLine): string => {
  if (!line.detail_dimension_type) return '—';
  return `${line.detail_dimension_type}: ${line.detail_dimension_value || ''}`;
};

const BudgetLineTable: React.FC<BudgetLineTableProps> = ({
  processedData,
  loading,
  isEmpty,
  filters,
  setFilter,
  sortField,
  sortDirection,
  handleSort,
  onRowClick,
}) => {
  const { t } = useTypedTranslation('budget');

  if (loading) {
    return (
      <Flex justify="center" py={10}>
        <Spinner size="lg" color="orange.300" />
      </Flex>
    );
  }

  if (isEmpty) {
    return <Text color="gray.400">{t('messages.noLines')}</Text>;
  }

  return (
    <Box overflowX="auto">
      <Table variant="simple" size="sm" bg="gray.800" color="white">
        <Thead>
          <Tr>
            <FilterableHeader
              label={t('columns.accountCode')}
              filterValue={filters.account_code}
              onFilterChange={(v) => setFilter('account_code', v)}
              sortable
              sortDirection={sortField === 'account_code' ? sortDirection : null}
              onSort={() => handleSort('account_code')}
            />
            <FilterableHeader
              label={t('columns.periodMode')}
              filterValue={filters.period_mode}
              onFilterChange={(v) => setFilter('period_mode', v)}
              sortable
              sortDirection={sortField === 'period_mode' ? sortDirection : null}
              onSort={() => handleSort('period_mode')}
            />
            <FilterableHeader
              label={t('columns.dimension')}
              filterValue={filters.dimension}
              onFilterChange={(v) => setFilter('dimension', v)}
              sortable
              sortDirection={sortField === 'dimension' ? sortDirection : null}
              onSort={() => handleSort('dimension')}
            />
            <FilterableHeader
              label={t('columns.total')}
              filterValue={filters.total}
              onFilterChange={(v) => setFilter('total', v)}
              sortable
              sortDirection={sortField === 'total' ? sortDirection : null}
              onSort={() => handleSort('total')}
              isNumeric
            />
          </Tr>
        </Thead>
        <Tbody>
          {processedData.map((row) => (
            <Tr
              key={row.id}
              _hover={{ bg: 'gray.700', cursor: 'pointer' }}
              onClick={() => onRowClick(row)}
            >
              <Td color="white">{row.account_code}</Td>
              <Td color="white">{row.period_mode}</Td>
              <Td color="white" display={{ base: 'none', md: 'table-cell' }}>
                {row.dimension}
              </Td>
              <Td color="white" isNumeric>
                {lineTotal(row).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
};

export default BudgetLineTable;
