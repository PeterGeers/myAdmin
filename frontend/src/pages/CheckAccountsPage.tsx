/**
 * CheckAccountsPage — Standalone page for Check Accounts validation.
 *
 * Extracted from BankingProcessor to be accessible directly from the
 * FIN > Validation menu. Uses the useCheckAccounts hook for all data
 * fetching, state, and handlers.
 *
 * @module pages/CheckAccountsPage
 * @see .kiro/specs/Common/navigation-restructure/requirements.md US-3
 */

import React from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
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
  Tooltip,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { useCheckAccounts } from '@/hooks/useCheckAccounts';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CheckAccountsPage: React.FC = () => {
  const {
    t,
    bankingBalances,
    checkingAccounts,
    sequenceResult,
    checkingSequence,
    expandedRows,
    endDate,
    setEndDate,
    sequenceStartDate,
    setSequenceStartDate,
    openingBalanceDate,
    selectedAccount,
    setSelectedAccount,
    lookupData,
    checkBankingAccounts,
    checkSequenceNumbers,
    toggleRowExpansion,
    handleKeyDown,
  } = useCheckAccounts();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box w="100%" p={4}>
      <VStack align="stretch" spacing={4}>
        {/* Header with actions */}
        <HStack justify="space-between">
          <Heading size="md">{t('checkAccounts.title')}</Heading>
          <HStack wrap="wrap" spacing={3}>
            <Button
              onClick={checkBankingAccounts}
              isLoading={checkingAccounts}
              colorScheme="blue"
              size="sm"
            >
              {t('checkAccounts.checkBalances')}
            </Button>
            <FormControl maxW="130px">
              <FormLabel color="white" fontSize="sm">
                {t('checkAccounts.endDate')}
              </FormLabel>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                onKeyDown={handleKeyDown}
                bg="gray.600"
                color="white"
                size="sm"
              />
            </FormControl>
            <Button
              onClick={checkSequenceNumbers}
              isLoading={checkingSequence}
              colorScheme="orange"
              size="sm"
            >
              {t('checkSequence.checkSequence')}
            </Button>
            <FormControl maxW="160px">
              <FormLabel color="white" fontSize="sm">
                {t('checkSequence.selectAccount')}
              </FormLabel>
              <Select
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
                bg="gray.600"
                color="white"
                size="sm"
              >
                {lookupData.bank_accounts.map((account) => (
                  <option
                    key={`${account.Account}-${account.administration}`}
                    value={`${account.Account}-${account.administration}`}
                  >
                    {account.Account} - {account.rekeningNummer}
                  </option>
                ))}
              </Select>
            </FormControl>
            <FormControl maxW="130px">
              <FormLabel color="white" fontSize="sm">
                Start Date
              </FormLabel>
              <Tooltip
                label="Set by annual closure"
                isDisabled={openingBalanceDate === null}
                placement="top"
                hasArrow
              >
                <Input
                  type="date"
                  value={sequenceStartDate}
                  onChange={(e) => setSequenceStartDate(e.target.value)}
                  onKeyDown={handleKeyDown}
                  isReadOnly={openingBalanceDate !== null}
                  bg={openingBalanceDate !== null ? 'gray.700' : 'gray.600'}
                  color="white"
                  size="sm"
                  cursor={openingBalanceDate !== null ? 'not-allowed' : undefined}
                />
              </Tooltip>
              {openingBalanceDate !== null && (
                <Text fontSize="xs" color="orange.300" mt={1}>
                  Set by annual closure
                </Text>
              )}
            </FormControl>
          </HStack>
        </HStack>

        {/* Balances Table */}
        {bankingBalances.length > 0 && (
          <BalancesTable
            bankingBalances={bankingBalances}
            expandedRows={expandedRows}
            toggleRowExpansion={toggleRowExpansion}
          />
        )}

        {/* Sequence Results */}
        {sequenceResult && <SequenceResults sequenceResult={sequenceResult} />}

        {/* Empty State */}
        {bankingBalances.length === 0 && !checkingAccounts && !sequenceResult && (
          <Text color="white" textAlign="center" py={8}>
            {t('checkAccounts.noAccounts')}
          </Text>
        )}
      </VStack>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface BalancesTableProps {
  bankingBalances: Array<{
    Reknum: string;
    Administration: string;
    calculated_balance: number;
    account_name: string;
    last_transaction_date: string;
    last_transactions: Array<{
      TransactionDescription: string;
      TransactionAmount: number;
      Debet: string;
      Credit: string;
      Ref2: string;
      Ref3: string;
    }>;
  }>;
  expandedRows: Set<string>;
  toggleRowExpansion: (key: string) => void;
}

const BalancesTable: React.FC<BalancesTableProps> = ({
  bankingBalances,
  expandedRows,
  toggleRowExpansion,
}) => (
  <TableContainer>
    <Table size="sm" variant="simple">
      <Thead>
        <Tr>
          <Th color="white" w="20px"></Th>
          <Th color="white">Administration</Th>
          <Th color="white">Account</Th>
          <Th color="white">Account Name</Th>
          <Th color="white" isNumeric>
            Calculated Balance
          </Th>
        </Tr>
      </Thead>
      <Tbody>
        {bankingBalances
          .sort((a, b) =>
            a.Administration !== b.Administration
              ? a.Administration.localeCompare(b.Administration)
              : a.Reknum.localeCompare(b.Reknum),
          )
          .map((balance) => {
            const rowKey = `${balance.Reknum}-${balance.Administration}`;
            const isExpanded = expandedRows.has(rowKey);
            return (
              <React.Fragment key={rowKey}>
                <Tr>
                  <Td color="white" fontSize="sm" w="20px">
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => toggleRowExpansion(rowKey)}
                      color="white"
                    >
                      {isExpanded ? '▼' : '▶'}
                    </Button>
                  </Td>
                  <Td color="white" fontSize="sm">
                    {balance.Administration}
                  </Td>
                  <Td color="white" fontSize="sm">
                    {balance.Reknum}
                  </Td>
                  <Td color="white" fontSize="sm">
                    {balance.account_name}
                  </Td>
                  <Td color="white" fontSize="sm" isNumeric>
                    €
                    {Number(balance.calculated_balance).toLocaleString('nl-NL', {
                      minimumFractionDigits: 2,
                    })}
                  </Td>
                </Tr>
                {isExpanded &&
                  balance.last_transactions &&
                  balance.last_transactions.length > 0 && (
                    <Tr>
                      <Td colSpan={5} p={0}>
                        <Box bg="gray.800" p={2}>
                          <Text color="white" fontSize="xs" mb={2} fontWeight="bold">
                            Last Transaction Date:{' '}
                            {balance.last_transaction_date
                              ? new Date(balance.last_transaction_date).toLocaleDateString('nl-NL')
                              : 'N/A'}
                          </Text>
                          <TableContainer>
                            <Table size="xs" variant="simple">
                              <Thead>
                                <Tr>
                                  <Th color="gray.300" fontSize="xs">
                                    Description
                                  </Th>
                                  <Th color="gray.300" fontSize="xs" isNumeric pr={4}>
                                    Amount
                                  </Th>
                                  <Th color="gray.300" fontSize="xs" pl={4}>
                                    Debet
                                  </Th>
                                  <Th color="gray.300" fontSize="xs">
                                    Credit
                                  </Th>
                                  <Th color="gray.300" fontSize="xs">
                                    Ref2
                                  </Th>
                                  <Th color="gray.300" fontSize="xs">
                                    Ref3
                                  </Th>
                                </Tr>
                              </Thead>
                              <Tbody>
                                {balance.last_transactions.map((transaction, txIndex) => (
                                  <Tr key={txIndex}>
                                    <Td
                                      color="gray.300"
                                      fontSize="xs"
                                      maxW="200px"
                                      isTruncated
                                      title={transaction.TransactionDescription}
                                    >
                                      {transaction.TransactionDescription}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs" isNumeric pr={4}>
                                      €
                                      {Number(transaction.TransactionAmount).toLocaleString('nl-NL', {
                                        minimumFractionDigits: 2,
                                      })}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs" pl={4}>
                                      {transaction.Debet}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs">
                                      {transaction.Credit}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs">
                                      {transaction.Ref2}
                                    </Td>
                                    <Td
                                      color="gray.300"
                                      fontSize="xs"
                                      maxW="100px"
                                      isTruncated
                                      title={transaction.Ref3}
                                    >
                                      {transaction.Ref3}
                                    </Td>
                                  </Tr>
                                ))}
                              </Tbody>
                            </Table>
                          </TableContainer>
                        </Box>
                      </Td>
                    </Tr>
                  )}
              </React.Fragment>
            );
          })}
      </Tbody>
    </Table>
  </TableContainer>
);

// ---------------------------------------------------------------------------

interface SequenceResultsProps {
  sequenceResult: {
    check_type: string;
    has_gaps: boolean;
    sequence_issues: Array<{
      expected: string;
      found: string;
      gap: number;
      date?: string;
      description?: string;
    }>;
    account_code: string;
    administration: string;
    iban: string;
    start_date: string;
    total_transactions: number;
    first_sequence?: number;
    last_sequence?: number;
    message?: string;
  };
}

const SequenceResults: React.FC<SequenceResultsProps> = ({ sequenceResult }) => (
  <Box bg="gray.800" p={4} borderRadius="md">
    <Heading size="sm" color="white" mb={3}>
      {sequenceResult.check_type === 'balance_comparison'
        ? 'Balance Check Results'
        : 'Sequence Check Results'}
    </Heading>
    <Grid templateColumns="repeat(2, 1fr)" gap={4} mb={4}>
      <Text color="white" fontSize="sm">
        Account: {sequenceResult.account_code} ({sequenceResult.administration})
      </Text>
      <Text color="white" fontSize="sm">
        IBAN: {sequenceResult.iban}
      </Text>
      <Text color="white" fontSize="sm">
        Since: {sequenceResult.start_date}
      </Text>
      <Text color="white" fontSize="sm">
        Total Transactions: {sequenceResult.total_transactions}
      </Text>
      {sequenceResult.check_type === 'balance_comparison' ? (
        <Text color="white" fontSize="sm" gridColumn="span 2">
          {sequenceResult.message}
        </Text>
      ) : (
        <Text color="white" fontSize="sm" gridColumn="span 2">
          Sequence Range: {sequenceResult.first_sequence} - {sequenceResult.last_sequence}
        </Text>
      )}
    </Grid>

    {sequenceResult.has_gaps ? (
      <Box>
        <Text color="red.300" fontWeight="bold" mb={2}>
          ⚠️ {sequenceResult.sequence_issues.length}{' '}
          {sequenceResult.check_type === 'balance_comparison'
            ? 'Balance Issues'
            : 'Sequence Issues'}{' '}
          Found:
        </Text>
        <TableContainer>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="gray.300" fontSize="xs">
                  Expected
                </Th>
                <Th color="gray.300" fontSize="xs">
                  Found
                </Th>
                <Th color="gray.300" fontSize="xs">
                  Gap
                </Th>
                <Th color="gray.300" fontSize="xs">
                  Date
                </Th>
                <Th color="gray.300" fontSize="xs">
                  Description
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {sequenceResult.sequence_issues.map((issue, index) => (
                <Tr key={index}>
                  <Td color="gray.300" fontSize="xs">
                    {issue.expected}
                  </Td>
                  <Td color="gray.300" fontSize="xs">
                    {issue.found}
                  </Td>
                  <Td color="gray.300" fontSize="xs">
                    {issue.gap > 0 ? `+${issue.gap}` : issue.gap}
                  </Td>
                  <Td color="gray.300" fontSize="xs">
                    {issue.date ? new Date(issue.date).toLocaleDateString('nl-NL') : ''}
                  </Td>
                  <Td
                    color="gray.300"
                    fontSize="xs"
                    maxW="200px"
                    isTruncated
                    title={issue.description}
                  >
                    {issue.description}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </TableContainer>
      </Box>
    ) : (
      <Text color="green.300" fontWeight="bold">
        {sequenceResult.check_type === 'balance_comparison'
          ? '✅ Balance matches — no discrepancies found!'
          : '✅ All sequence numbers are consecutive - no gaps found!'}
      </Text>
    )}
  </Box>
);

export default CheckAccountsPage;
