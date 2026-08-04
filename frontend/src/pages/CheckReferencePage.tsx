/**
 * CheckReferencePage — Standalone page for Check Reference validation.
 *
 * Extracted from BankingProcessor to be accessible directly from the
 * FIN > Validation menu. Uses the useCheckReference hook for all data
 * fetching, state, and handlers.
 *
 * @module pages/CheckReferencePage
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-3
 */

import React from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Heading,
  Input,
  Select,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { FilterableHeader } from '@/components/filters/FilterableHeader';
import { useCheckReference } from '@/hooks/useCheckReference';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a number as Dutch-locale currency */
const formatAmount = (amount: number): string => {
  const num = Number(amount) || 0;
  return `€${num.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CheckReferencePage: React.FC = () => {
  const {
    t,
    loading,
    currentTenant,
    checkRefFilters,
    setCheckRefFilters,
    availableLedgers,
    refSummaryData,
    refSummaryFilters,
    setRefSummaryFilter,
    handleRefSummarySort,
    refSummarySortField,
    refSummarySortDirection,
    processedRefSummary,
    selectedReference,
    selectedReferenceDetails,
    refDetailsFilters,
    setRefDetailsFilter,
    handleRefDetailsSort,
    refDetailsSortField,
    refDetailsSortDirection,
    processedRefDetails,
    fetchCheckRefData,
    fetchReferenceDetails,
  } = useCheckReference();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box w="100%" p={4}>
      <VStack align="stretch" spacing={4}>
        {/* Header */}
        <Heading size="md">Check Reference Numbers</Heading>

        {/* Filters */}
        <Box bg="gray.800" p={4} borderRadius="md">
          <HStack spacing={4} wrap="wrap">
            <FormControl maxW="180px">
              <FormLabel color="white" fontSize="sm">
                Administration
              </FormLabel>
              <Input
                value={currentTenant || checkRefFilters.administration}
                isReadOnly
                bg="gray.700"
                color="white"
                size="sm"
                cursor="not-allowed"
              />
            </FormControl>
            <FormControl maxW="150px">
              <FormLabel color="white" fontSize="sm">
                Ledger
              </FormLabel>
              <Select
                value={checkRefFilters.ledger}
                onChange={(e) =>
                  setCheckRefFilters((prev) => ({ ...prev, ledger: e.target.value }))
                }
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="all">All</option>
                {availableLedgers.map((ledger) => (
                  <option key={ledger} value={ledger}>
                    {ledger}
                  </option>
                ))}
              </Select>
            </FormControl>
            <Button
              onClick={fetchCheckRefData}
              isLoading={loading}
              colorScheme="green"
              size="sm"
              alignSelf="flex-end"
            >
              Check References
            </Button>
          </HStack>
        </Box>

        {/* Summary Table */}
        {refSummaryData.length > 0 && (
          <RefSummaryTable
            processedRefSummary={processedRefSummary}
            refSummaryData={refSummaryData}
            refSummaryFilters={refSummaryFilters}
            setRefSummaryFilter={setRefSummaryFilter}
            refSummarySortField={refSummarySortField}
            refSummarySortDirection={refSummarySortDirection}
            handleRefSummarySort={handleRefSummarySort}
            selectedReference={selectedReference}
            fetchReferenceDetails={fetchReferenceDetails}
          />
        )}

        {/* Detail Table */}
        {selectedReferenceDetails.length > 0 && (
          <RefDetailsTable
            selectedReference={selectedReference}
            processedRefDetails={processedRefDetails}
            refDetailsFilters={refDetailsFilters}
            setRefDetailsFilter={setRefDetailsFilter}
            refDetailsSortField={refDetailsSortField}
            refDetailsSortDirection={refDetailsSortDirection}
            handleRefDetailsSort={handleRefDetailsSort}
          />
        )}

        {/* Empty State */}
        {refSummaryData.length === 0 && !loading && (
          <Text color="white" textAlign="center" py={8}>
            Use the button above to check reference numbers
          </Text>
        )}
      </VStack>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface RefSummaryTableProps {
  processedRefSummary: Array<{
    ReferenceNumber: string;
    transaction_count: number;
    total_amount: string | number;
  }>;
  refSummaryData: Array<{ total_amount: string | number }>;
  refSummaryFilters: Record<string, string>;
  setRefSummaryFilter: (key: string, value: string) => void;
  refSummarySortField: string | null;
  refSummarySortDirection: 'asc' | 'desc' | null;
  handleRefSummarySort: (field: string) => void;
  selectedReference: string;
  fetchReferenceDetails: (referenceNumber: string) => void;
}

const RefSummaryTable: React.FC<RefSummaryTableProps> = ({
  processedRefSummary,
  refSummaryData,
  refSummaryFilters,
  setRefSummaryFilter,
  refSummarySortField,
  refSummarySortDirection,
  handleRefSummarySort,
  selectedReference,
  fetchReferenceDetails,
}) => (
  <Box bg="gray.800" p={4} borderRadius="md">
    <VStack align="stretch" spacing={4}>
      <HStack justify="space-between">
        <Heading size="xs" color="white">
          Reference Summary ({processedRefSummary.length})
        </Heading>
        <Text color="orange.300" fontWeight="bold" fontSize="sm">
          Total:{' '}
          {formatAmount(
            refSummaryData.reduce(
              (sum, row) => sum + (parseFloat(String(row.total_amount)) || 0),
              0,
            ),
          )}
        </Text>
      </HStack>
      <TableContainer maxH="300px" overflowY="auto">
        <Table size="sm" variant="simple">
          <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
            <Tr>
              <FilterableHeader
                label="Reference"
                filterValue={refSummaryFilters.ReferenceNumber}
                onFilterChange={(v) => setRefSummaryFilter('ReferenceNumber', v)}
                sortable
                sortDirection={
                  refSummarySortField === 'ReferenceNumber' ? refSummarySortDirection : null
                }
                onSort={() => handleRefSummarySort('ReferenceNumber')}
              />
              <FilterableHeader
                label="Count"
                filterValue={refSummaryFilters.transaction_count}
                onFilterChange={(v) => setRefSummaryFilter('transaction_count', v)}
                sortable
                sortDirection={
                  refSummarySortField === 'transaction_count' ? refSummarySortDirection : null
                }
                onSort={() => handleRefSummarySort('transaction_count')}
                isNumeric
              />
              <FilterableHeader
                label="Total Amount"
                filterValue={refSummaryFilters.total_amount}
                onFilterChange={(v) => setRefSummaryFilter('total_amount', v)}
                sortable
                sortDirection={
                  refSummarySortField === 'total_amount' ? refSummarySortDirection : null
                }
                onSort={() => handleRefSummarySort('total_amount')}
                isNumeric
              />
            </Tr>
          </Thead>
          <Tbody>
            {processedRefSummary.map((row, index) => (
              <Tr
                key={index}
                onClick={() => fetchReferenceDetails(row.ReferenceNumber)}
                _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                bg={selectedReference === row.ReferenceNumber ? 'gray.600' : 'transparent'}
              >
                <Td color="white" fontSize="xs" maxW="200px" isTruncated title={row.ReferenceNumber}>
                  {row.ReferenceNumber}
                </Td>
                <Td color="white" fontSize="xs" isNumeric>
                  {row.transaction_count}
                </Td>
                <Td color="white" fontSize="xs" isNumeric>
                  {formatAmount(Number(row.total_amount))}
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </TableContainer>
    </VStack>
  </Box>
);

// ---------------------------------------------------------------------------

interface RefDetailsTableProps {
  selectedReference: string;
  processedRefDetails: Array<{
    TransactionNumber?: string;
    TransactionDate?: string;
    Amount?: string | number;
    TransactionDescription?: string;
  }>;
  refDetailsFilters: Record<string, string>;
  setRefDetailsFilter: (key: string, value: string) => void;
  refDetailsSortField: string | null;
  refDetailsSortDirection: 'asc' | 'desc' | null;
  handleRefDetailsSort: (field: string) => void;
}

const RefDetailsTable: React.FC<RefDetailsTableProps> = ({
  selectedReference,
  processedRefDetails,
  refDetailsFilters,
  setRefDetailsFilter,
  refDetailsSortField,
  refDetailsSortDirection,
  handleRefDetailsSort,
}) => (
  <Box bg="gray.800" p={4} borderRadius="md">
    <Heading size="xs" color="white" mb={2}>
      Transactions for Reference: {selectedReference} ({processedRefDetails.length})
    </Heading>
    <TableContainer maxH="300px" overflowY="auto">
      <Table size="sm" variant="simple">
        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
          <Tr>
            <FilterableHeader
              label="Transaction Number"
              filterValue={refDetailsFilters.TransactionNumber}
              onFilterChange={(v) => setRefDetailsFilter('TransactionNumber', v)}
              sortable
              sortDirection={
                refDetailsSortField === 'TransactionNumber' ? refDetailsSortDirection : null
              }
              onSort={() => handleRefDetailsSort('TransactionNumber')}
            />
            <FilterableHeader
              label="Date"
              filterValue={refDetailsFilters.TransactionDate}
              onFilterChange={(v) => setRefDetailsFilter('TransactionDate', v)}
              sortable
              sortDirection={
                refDetailsSortField === 'TransactionDate' ? refDetailsSortDirection : null
              }
              onSort={() => handleRefDetailsSort('TransactionDate')}
            />
            <FilterableHeader
              label="Amount"
              filterValue={refDetailsFilters.Amount}
              onFilterChange={(v) => setRefDetailsFilter('Amount', v)}
              sortable
              sortDirection={refDetailsSortField === 'Amount' ? refDetailsSortDirection : null}
              onSort={() => handleRefDetailsSort('Amount')}
              isNumeric
            />
            <FilterableHeader
              label="Description"
              filterValue={refDetailsFilters.TransactionDescription}
              onFilterChange={(v) => setRefDetailsFilter('TransactionDescription', v)}
              sortable
              sortDirection={
                refDetailsSortField === 'TransactionDescription' ? refDetailsSortDirection : null
              }
              onSort={() => handleRefDetailsSort('TransactionDescription')}
            />
          </Tr>
        </Thead>
        <Tbody>
          {processedRefDetails.map((transaction, index) => (
            <Tr key={index}>
              <Td color="white" fontSize="xs">
                {transaction.TransactionNumber || '-'}
              </Td>
              <Td color="white" fontSize="xs">
                {transaction.TransactionDate
                  ? new Date(transaction.TransactionDate).toISOString().split('T')[0]
                  : '-'}
              </Td>
              <Td color="white" fontSize="xs" isNumeric>
                {formatAmount(Number(transaction.Amount ?? 0))}
              </Td>
              <Td
                color="white"
                fontSize="xs"
                maxW="300px"
                isTruncated
                title={transaction.TransactionDescription}
              >
                {transaction.TransactionDescription}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </TableContainer>
  </Box>
);

export default CheckReferencePage;
