/**
 * BankingMutatiesTab Component
 *
 * Extracted from BankingProcessor — renders the Mutaties tab with
 * parameter-driven column configuration, inline column filters, and sorting.
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useTableConfig('banking_mutaties') for parameter-driven column/filter config
 * - useFilterableTable for combined filtering + sorting
 * - FilterableHeader for inline column text filters with sort indicators
 * - FilterPanel retained above the table for year multi-select and display limit
 *
 * @module banking/BankingMutatiesTab
 * @see .kiro/specs/table-filter-framework-v2/design.md §Pattern C
 */

import React, { useMemo } from 'react';
import {
  Button,
  HStack,
  Heading,
  Table,
  TableContainer,
  Tbody,
  Td,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import FilterPanel from '../filters/FilterPanel';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { useTableConfig } from '../../hooks/useTableConfig';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Transaction {
  ID?: number;
  row_id: number;
  TransactionNumber: string;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string;
  Ref2: string;
  Ref3: string;
  Ref4: string;
  Administration: string;
}

export interface BankingMutatiesTabProps {
  /** Raw mutaties data from the API */
  mutaties: Transaction[];
  /** Available filter options (years list) */
  filterOptions: { years: string[]; administrations: string[] };
  /** Current year filter state */
  mutatiesFilters: { years: string[] };
  /** Setter for year filter state */
  setMutatiesFilters: React.Dispatch<React.SetStateAction<{ years: string[] }>>;
  /** Open the edit modal for a transaction */
  openEditModal: (record: Transaction) => void;
  /** Open the insert modal for a new transaction */
  openInsertModal: () => void;
  /** Copy text to clipboard with feedback */
  copyToClipboard: (text: string) => void;
  /** Handle Ref3 click (open URL or copy) */
  handleRef3Click: (ref3: string) => void;
}

// ---------------------------------------------------------------------------
// Column label mapping
// ---------------------------------------------------------------------------

const COLUMN_LABELS: Record<string, string> = {
  ID: 'ID',
  TransactionNumber: 'Trx Number',
  TransactionDate: 'Date',
  TransactionDescription: 'Description',
  TransactionAmount: 'Amount',
  Debet: 'Debit',
  Credit: 'Credit',
  ReferenceNumber: 'Reference',
  Ref1: 'Ref1',
  Ref2: 'Ref2',
  Ref3: 'Ref3',
  Ref4: 'Ref4',
  Administration: 'Administration',
};

// ---------------------------------------------------------------------------
// Cell renderer
// ---------------------------------------------------------------------------

interface CellProps {
  col: string;
  mutatie: Transaction;
  copyToClipboard: (text: string) => void;
  handleRef3Click: (ref3: string) => void;
}

const MutatieCell: React.FC<CellProps> = ({ col, mutatie, copyToClipboard, handleRef3Click }) => {
  const value = mutatie[col as keyof Transaction];

  // Special rendering per column
  switch (col) {
    case 'TransactionDate':
      return (
        <Td color="white" fontSize="sm">
          {value ? new Date(value as string).toLocaleDateString('nl-NL') : ''}
        </Td>
      );
    case 'TransactionAmount':
      return (
        <Td color="white" fontSize="sm">
          €{Number(value).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
        </Td>
      );
    case 'TransactionDescription':
      return (
        <Td
          color="white"
          fontSize="sm"
          maxW="225px"
          isTruncated
          title={String(value || '')}
          cursor="pointer"
          onClick={(e) => { e.stopPropagation(); copyToClipboard(String(value || '')); }}
        >
          {String(value || '')}
        </Td>
      );
    case 'ReferenceNumber':
    case 'Ref1':
    case 'Ref2':
    case 'Ref4':
      return (
        <Td
          color="white"
          fontSize="sm"
          maxW="100px"
          isTruncated
          title={String(value || '')}
          cursor="pointer"
          onClick={(e) => { e.stopPropagation(); copyToClipboard(String(value || '')); }}
        >
          {String(value || '')}
        </Td>
      );
    case 'Ref3':
      return (
        <Td
          color="white"
          fontSize="sm"
          maxW="100px"
          isTruncated
          title={String(value || '')}
          cursor="pointer"
          onClick={(e) => { e.stopPropagation(); handleRef3Click(String(value || '')); }}
        >
          {String(value || '')}
        </Td>
      );
    default:
      return (
        <Td color="white" fontSize="sm">
          {String(value ?? '')}
        </Td>
      );
  }
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BankingMutatiesTab: React.FC<BankingMutatiesTabProps> = ({
  mutaties,
  filterOptions,
  mutatiesFilters,
  setMutatiesFilters,
  openEditModal,
  openInsertModal,
  copyToClipboard,
  handleRef3Click,
}) => {
  const { t } = useTypedTranslation('banking');

  // Parameter-driven table configuration
  const tableConfig = useTableConfig('banking_mutaties');

  // Display limit (kept local — not part of column filter framework)
  const [displayLimit, setDisplayLimit] = React.useState(100);

  // Build initial filters from configured filterable columns
  const initialFilters = useMemo(
    () => Object.fromEntries(tableConfig.filterableColumns.map((col) => [col, ''])),
    [tableConfig.filterableColumns],
  );

  // Combined filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    resetFilters,
    hasActiveFilters,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<Transaction>(mutaties, {
    initialFilters,
    defaultSort: tableConfig.defaultSort,
  });

  // Apply display limit after filtering + sorting
  const displayedData = useMemo(
    () => processedData.slice(0, displayLimit),
    [processedData, displayLimit],
  );

  return (
    <VStack align="stretch" spacing={4}>
      {/* Above-table filters: year multi-select + display limit (hybrid approach) */}
      <FilterPanel
        layout="horizontal"
        filters={[
          {
            type: 'multi' as const,
            label: 'Year',
            options: filterOptions.years,
            value: mutatiesFilters.years,
            onChange: (years: string[]) => setMutatiesFilters((prev) => ({ ...prev, years })),
          },
          {
            type: 'single' as const,
            label: 'Records to show',
            options: [50, 100, 250, 500, 1000, 99999],
            value: displayLimit,
            onChange: (value: number) => setDisplayLimit(Number(value)),
            getOptionLabel: (val: number) => (val === 99999 ? 'All' : String(val)),
            getOptionValue: (val: number) => String(val),
          },
        ]}
        labelColor="white"
        bg="gray.600"
        color="white"
      />

      <HStack justify="space-between" align="center">
        <HStack spacing={4}>
          <Heading size="md">
            Mutaties ({displayedData.length} of {mutaties.length})
          </Heading>
          {hasActiveFilters && (
            <Button variant="link" colorScheme="orange" onClick={resetFilters} size="sm">
              Clear filters
            </Button>
          )}
        </HStack>
        <Button
          colorScheme="green"
          size="sm"
          leftIcon={<span>+</span>}
          onClick={openInsertModal}
        >
          {t('mutaties.addNewRecord')}
        </Button>
      </HStack>

      <TableContainer maxH="600px" overflowY="auto" overflowX="auto">
        <Table size="sm" variant="simple">
          <Thead position="sticky" top={0} zIndex={1}>
            <Tr>
              {tableConfig.columns.map((col) => {
                const isFilterable = tableConfig.filterableColumns.includes(col);
                return (
                  <FilterableHeader
                    key={col}
                    label={COLUMN_LABELS[col] || col}
                    filterValue={isFilterable ? filters[col] : undefined}
                    onFilterChange={isFilterable ? (v) => setFilter(col, v) : undefined}
                    sortable
                    sortDirection={sortField === col ? sortDirection : null}
                    onSort={() => handleSort(col)}
                    placeholder={`Filter...`}
                    isNumeric={col === 'TransactionAmount'}
                  />
                );
              })}
            </Tr>
          </Thead>
          <Tbody>
            {displayedData.map((mutatie) => (
              <Tr
                key={mutatie.ID}
                _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                onClick={() => openEditModal(mutatie)}
              >
                {tableConfig.columns.map((col) => (
                  <MutatieCell
                    key={col}
                    col={col}
                    mutatie={mutatie}
                    copyToClipboard={copyToClipboard}
                    handleRef3Click={handleRef3Click}
                  />
                ))}
              </Tr>
            ))}
          </Tbody>
        </Table>
      </TableContainer>
    </VStack>
  );
};

export default BankingMutatiesTab;
