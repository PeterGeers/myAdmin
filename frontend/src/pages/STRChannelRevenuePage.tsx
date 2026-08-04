/**
 * STRChannelRevenuePage — Standalone page for STR Channel Revenue calculation.
 *
 * Extracted from BankingProcessor to be accessible directly from the
 * FIN > Import menu. Uses the useStrChannelRevenue hook for all data
 * fetching, state, and handlers.
 *
 * Creates journal entries: amounts_received → 8003, 8003 → 2020
 *
 * @module pages/STRChannelRevenuePage
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-4
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
  Th,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { useStrChannelRevenue } from '@/hooks/useStrChannelRevenue';
import type { StrChannelPreviewRow, StrChannelTransaction, StrChannelSummary } from '@/hooks/useStrChannelRevenue';

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

const formatAmount = (amount: number): string => {
  const num = Number(amount) || 0;
  return `€${num.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}`;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const STRChannelRevenuePage: React.FC = () => {
  const {
    t,
    currentTenant,
    isVisible,
    loading,
    strChannelFilters,
    setStrChannelFilters,
    strChannelPreview,
    strChannelTransactions,
    strChannelSummary,
    fetchStrChannelPreview,
    calculateStrChannelRevenue,
    saveStrChannelTransactions,
    handleKeyDown,
  } = useStrChannelRevenue();

  // If tenant doesn't have str_channel_revenue function, show nothing
  if (!isVisible) {
    return (
      <Box w="100%" p={4}>
        <Text color="white" textAlign="center" py={8}>
          {t('strChannel.noChannels')}
        </Text>
      </Box>
    );
  }

  return (
    <Box w="100%" p={4}>
      <VStack align="stretch" spacing={4}>
        <Box bg="gray.800" p={4} borderRadius="md">
          <Heading size="sm" color="white" mb={4}>
            {t('strChannel.title')}
          </Heading>
          <Text color="gray.300" fontSize="sm" mb={4}>
            {t('labels.calculateMonthlyRevenue')}
          </Text>

          {/* Filters */}
          <HStack spacing={4} mb={4} wrap="wrap">
            <FormControl maxW="120px">
              <FormLabel color="white" fontSize="sm">
                {t('strChannel.year')}
              </FormLabel>
              <Input
                type="number"
                value={strChannelFilters.year}
                onChange={(e) =>
                  setStrChannelFilters((prev) => ({
                    ...prev,
                    year: parseInt(e.target.value) || new Date().getFullYear(),
                  }))
                }
                onKeyDown={handleKeyDown}
                bg="gray.600"
                color="white"
                size="sm"
              />
            </FormControl>
            <FormControl maxW="120px">
              <FormLabel color="white" fontSize="sm">
                {t('strChannel.month')}
              </FormLabel>
              <Select
                value={strChannelFilters.month}
                onChange={(e) =>
                  setStrChannelFilters((prev) => ({
                    ...prev,
                    month: parseInt(e.target.value),
                  }))
                }
                bg="gray.600"
                color="white"
                size="sm"
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
                  <option key={month} value={month}>
                    {new Date(2000, month - 1).toLocaleString('default', { month: 'long' })}
                  </option>
                ))}
              </Select>
            </FormControl>
            <FormControl maxW="180px">
              <FormLabel color="white" fontSize="sm">
                {t('strChannel.administration')}
              </FormLabel>
              <Input
                value={currentTenant || strChannelFilters.administration}
                isReadOnly
                bg="gray.700"
                color="white"
                size="sm"
                cursor="not-allowed"
              />
            </FormControl>
            <Button
              onClick={fetchStrChannelPreview}
              isLoading={loading}
              colorScheme="blue"
              size="sm"
              alignSelf="flex-end"
            >
              {t('strChannel.previewData')}
            </Button>
            <Button
              onClick={calculateStrChannelRevenue}
              isLoading={loading}
              colorScheme="green"
              size="sm"
              alignSelf="flex-end"
              isDisabled={strChannelPreview.length === 0}
            >
              {t('strChannel.calculateRevenue')}
            </Button>
          </HStack>

          {/* Preview Table */}
          {strChannelPreview.length > 0 && (
            <PreviewTable preview={strChannelPreview} />
          )}

          {/* Proposed Transactions */}
          {strChannelTransactions.length > 0 && (
            <ProposedTransactions
              transactions={strChannelTransactions}
              summary={strChannelSummary}
              loading={loading}
              onSave={saveStrChannelTransactions}
            />
          )}
        </Box>

        {/* Empty State */}
        {strChannelPreview.length === 0 && strChannelTransactions.length === 0 && (
          <Text color="white" textAlign="center" py={8}>
            {t('strChannel.noChannels')}
          </Text>
        )}
      </VStack>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PreviewTableProps {
  preview: StrChannelPreviewRow[];
}

const PreviewTable: React.FC<PreviewTableProps> = ({ preview }) => (
  <VStack align="stretch" spacing={4}>
    <Heading size="xs" color="white">
      Channel Data Preview ({preview.length})
    </Heading>
    <TableContainer maxH="200px" overflowY="auto">
      <Table size="sm" variant="simple">
        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
          <Tr>
            <Th color="white" fontSize="xs">Channel</Th>
            <Th color="white" fontSize="xs">Account</Th>
            <Th color="white" fontSize="xs" isNumeric>Transactions</Th>
            <Th color="white" fontSize="xs" isNumeric>Total Amount</Th>
            <Th color="white" fontSize="xs">Date Range</Th>
          </Tr>
        </Thead>
        <Tbody>
          {preview.map((row, index) => (
            <Tr key={index}>
              <Td color="white" fontSize="xs">
                {String(row.ReferenceNumber ?? '')}
              </Td>
              <Td color="white" fontSize="xs">
                {String(row.Reknum ?? '')}
              </Td>
              <Td color="white" fontSize="xs" isNumeric>
                {String(row.transaction_count ?? '')}
              </Td>
              <Td color="white" fontSize="xs" isNumeric>
                {formatAmount(Number(row.total_amount ?? 0))}
              </Td>
              <Td color="white" fontSize="xs">
                {row.first_date
                  ? new Date(String(row.first_date)).toLocaleDateString('nl-NL')
                  : '-'}{' '}
                -{' '}
                {row.last_date
                  ? new Date(String(row.last_date)).toLocaleDateString('nl-NL')
                  : '-'}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </TableContainer>
  </VStack>
);

// ---------------------------------------------------------------------------

interface ProposedTransactionsProps {
  transactions: StrChannelTransaction[];
  summary: StrChannelSummary | null;
  loading: boolean;
  onSave: () => void;
}

const ProposedTransactions: React.FC<ProposedTransactionsProps> = ({
  transactions,
  summary,
  loading,
  onSave,
}) => (
  <VStack align="stretch" spacing={4}>
    <HStack justify="space-between">
      <Heading size="xs" color="white">
        Proposed Transactions ({transactions.length})
      </Heading>
      <Button onClick={onSave} isLoading={loading} colorScheme="orange" size="sm">
        Save to Database
      </Button>
    </HStack>

    {summary && (
      <Box bg="gray.700" p={3} borderRadius="md">
        <Text color="white" fontSize="sm">
          <strong>Reference:</strong> {summary.ref1} |{' '}
          <strong>Period:</strong> {summary.month}/{summary.year} |{' '}
          <strong>End Date:</strong> {summary.end_date}
        </Text>
      </Box>
    )}

    <TableContainer maxH="400px" overflowY="auto">
      <Table size="sm" variant="simple">
        <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
          <Tr>
            <Th color="white" fontSize="xs">Date</Th>
            <Th color="white" fontSize="xs">Description</Th>
            <Th color="white" fontSize="xs" isNumeric>Amount</Th>
            <Th color="white" fontSize="xs">Debet</Th>
            <Th color="white" fontSize="xs">Credit</Th>
            <Th color="white" fontSize="xs">Reference</Th>
          </Tr>
        </Thead>
        <Tbody>
          {transactions.map((transaction, index) => (
            <Tr key={index}>
              <Td color="white" fontSize="xs">
                {transaction.TransactionDate}
              </Td>
              <Td
                color="white"
                fontSize="xs"
                maxW="200px"
                isTruncated
                title={transaction.TransactionDescription}
              >
                {transaction.TransactionDescription}
              </Td>
              <Td color="white" fontSize="xs" isNumeric>
                {formatAmount(Number(transaction.TransactionAmount ?? 0))}
              </Td>
              <Td color="white" fontSize="xs">
                {transaction.Debet}
              </Td>
              <Td color="white" fontSize="xs">
                {transaction.Credit}
              </Td>
              <Td color="white" fontSize="xs">
                {transaction.ReferenceNumber}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </TableContainer>
  </VStack>
);

export default STRChannelRevenuePage;
