/**
 * BankingProcessorTable Component
 *
 * Extracted from BankingProcessor — renders the editable transaction review table
 * shown after CSV file processing. Users review, edit, and approve transactions
 * before saving them to the database.
 *
 * Features:
 * - Two-row layout per transaction (main fields + reference fields)
 * - Inline editing of all fields
 * - AccountSelect dropdowns for Debet/Credit with chart-of-accounts lookup
 * - Pattern-filled field highlighting (blue border for auto-filled fields)
 * - Form validation with error messages
 * - ENTER key navigation between fields
 *
 * @module BankingProcessorTable
 */

import React from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  FormControl,
  FormErrorMessage,
  Grid,
  HStack,
  Heading,
  Input,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from '@chakra-ui/react';
import { FieldHelp } from './help';
import AccountSelect from './common/AccountSelect';
import type { Transaction } from './BankingProcessor';
import type { AccountOption } from '../hooks/useAccountLookup';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatternResults {
  patterns_found: number;
  predictions_made: {
    debet: number;
    credit: number;
    reference: number;
  };
  confidence_scores: number[];
  average_confidence: number;
  enhanced_results?: unknown;
}

export interface BankingProcessorTableProps {
  /** Transactions to display in the review table */
  transactions: Transaction[];
  /** Chart of accounts for the AccountSelect dropdowns */
  chartAccounts: AccountOption[];
  /** Whether a loading operation is in progress */
  loading: boolean;
  /** Pattern analysis results to display summary card */
  patternResults: PatternResults | null;
  /** Callback to update a single field on a transaction */
  updateTransaction: (rowId: number, field: keyof Transaction, value: string | number) => void;
  /** Callback to apply pattern matching */
  onApplyPatterns: () => void;
  /** Callback to save transactions (triggers confirmation) */
  onSaveTransactions: () => void;
  /** Get pattern field styling for a transaction field */
  getPatternFieldStyle: (transaction: Transaction, field: string) => Record<string, unknown>;
  /** Translation function */
  t: (key: string, options?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Pattern Results Card
// ---------------------------------------------------------------------------

interface PatternResultsCardProps {
  patternResults: PatternResults;
  t: (key: string, options?: Record<string, unknown>) => string;
}

const PatternResultsCard: React.FC<PatternResultsCardProps> = ({ patternResults, t }) => (
  <Card mb={6} bg="blue.50" borderColor="blue.200" borderWidth="1px">
    <CardBody>
      <Heading size="sm" mb={3} color="blue.800">{t('labels.patternResultsTitle')}</Heading>
      <Grid templateColumns="repeat(2, 1fr)" gap={4}>
        <Box>
          <Text fontSize="sm" color="blue.700">
            <strong>{t('labels.patternsFound')}:</strong> {patternResults.patterns_found}
          </Text>
          <Text fontSize="sm" color="blue.700">
            <strong>{t('labels.debetPredictions')}:</strong> {patternResults.predictions_made?.debet || 0}
          </Text>
          <Text fontSize="sm" color="blue.700">
            <strong>{t('labels.creditPredictions')}:</strong> {patternResults.predictions_made?.credit || 0}
          </Text>
        </Box>
        <Box>
          <Text fontSize="sm" color="blue.700">
            <strong>{t('labels.referencePredictions')}:</strong> {patternResults.predictions_made?.reference || 0}
          </Text>
          <Text fontSize="sm" color="blue.700">
            <strong>{t('labels.averageConfidence')}:</strong> {(patternResults.average_confidence * 100).toFixed(1)}%
          </Text>
          <Text fontSize="xs" color="blue.600" mt={2}>
            {t('labels.fieldsAutoFilled')}
          </Text>
        </Box>
      </Grid>
    </CardBody>
  </Card>
);

// ---------------------------------------------------------------------------
// Key handler utility
// ---------------------------------------------------------------------------

/** Handle ENTER key to move focus to next input field instead of submitting form */
const handleKeyDown = (e: React.KeyboardEvent) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const form = e.currentTarget.closest('form');
    if (form) {
      const inputs = Array.from(form.querySelectorAll('input, select, textarea')) as HTMLElement[];
      const currentIndex = inputs.indexOf(e.currentTarget as HTMLElement);
      const nextInput = inputs[currentIndex + 1];
      if (nextInput) {
        nextInput.focus();
      }
    }
  }
};

// ---------------------------------------------------------------------------
// Transaction Row
// ---------------------------------------------------------------------------

interface TransactionRowProps {
  transaction: Transaction;
  index: number;
  chartAccounts: AccountOption[];
  updateTransaction: (rowId: number, field: keyof Transaction, value: string | number) => void;
  getPatternFieldStyle: (transaction: Transaction, field: string) => Record<string, unknown>;
  t: (key: string, options?: Record<string, unknown>) => string;
}

const TransactionRow: React.FC<TransactionRowProps> = ({
  transaction,
  index,
  chartAccounts,
  updateTransaction,
  getPatternFieldStyle,
  t,
}) => {
  const bgColor = index % 2 === 0 ? 'gray.100' : 'white';

  return (
    <React.Fragment>
      {/* Main row: TrxNumber, Date, Description, Amount, Debet, Credit */}
      <Tr bg={bgColor}>
        <Td>
          <Input
            size="sm"
            value={transaction.TransactionNumber}
            onChange={(e) => updateTransaction(transaction.row_id, 'TransactionNumber', e.target.value)}
            onKeyDown={handleKeyDown}
            minW="120px"
          />
        </Td>
        <Td>
          <FormControl isInvalid={!transaction.TransactionDate}>
            <Input
              size="sm"
              type="date"
              value={transaction.TransactionDate}
              onChange={(e) => updateTransaction(transaction.row_id, 'TransactionDate', e.target.value)}
              onKeyDown={handleKeyDown}
              isInvalid={!transaction.TransactionDate}
            />
            {!transaction.TransactionDate && (
              <FormErrorMessage fontSize="xs">{t('labels.required')}</FormErrorMessage>
            )}
          </FormControl>
        </Td>
        <Td>
          <FormControl isInvalid={!transaction.TransactionDescription}>
            <Input
              size="sm"
              value={transaction.TransactionDescription}
              onChange={(e) => updateTransaction(transaction.row_id, 'TransactionDescription', e.target.value)}
              onKeyDown={handleKeyDown}
              minW="200px"
              isInvalid={!transaction.TransactionDescription}
            />
            {!transaction.TransactionDescription && (
              <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
            )}
          </FormControl>
        </Td>
        <Td>
          <FormControl isInvalid={!transaction.TransactionAmount || transaction.TransactionAmount <= 0}>
            <Input
              size="sm"
              type="number"
              step="0.01"
              value={transaction.TransactionAmount}
              onChange={(e) => updateTransaction(transaction.row_id, 'TransactionAmount', parseFloat(e.target.value) || 0)}
              onKeyDown={handleKeyDown}
              isInvalid={!transaction.TransactionAmount || transaction.TransactionAmount <= 0}
            />
            {(!transaction.TransactionAmount || transaction.TransactionAmount <= 0) && (
              <FormErrorMessage fontSize="xs">Must be greater than 0</FormErrorMessage>
            )}
          </FormControl>
        </Td>
        <Td>
          <FormControl isInvalid={!transaction.Debet}>
            <AccountSelect
              size="sm"
              value={transaction.Debet}
              onChange={(val) => updateTransaction(transaction.row_id, 'Debet', val)}
              accounts={chartAccounts}
              onKeyDown={handleKeyDown}
              isInvalid={!transaction.Debet}
              {...getPatternFieldStyle(transaction, 'debet')}
            />
            {!transaction.Debet && (
              <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
            )}
          </FormControl>
        </Td>
        <Td>
          <FormControl isInvalid={!transaction.Credit}>
            <AccountSelect
              size="sm"
              value={transaction.Credit}
              onChange={(val) => updateTransaction(transaction.row_id, 'Credit', val)}
              accounts={chartAccounts}
              onKeyDown={handleKeyDown}
              isInvalid={!transaction.Credit}
              {...getPatternFieldStyle(transaction, 'credit')}
            />
            {!transaction.Credit && (
              <FormErrorMessage fontSize="xs">Required</FormErrorMessage>
            )}
          </FormControl>
        </Td>
      </Tr>
      {/* Reference row: RefNumber, Ref1, Ref2, Administration */}
      <Tr bg={bgColor}>
        <Td>
          <Input
            size="sm"
            value={transaction.ReferenceNumber}
            onChange={(e) => updateTransaction(transaction.row_id, 'ReferenceNumber', e.target.value)}
            onKeyDown={handleKeyDown}
            minW="120px"
            {...getPatternFieldStyle(transaction, 'reference')}
          />
        </Td>
        <Td>
          <Input
            size="sm"
            value={transaction.Ref1}
            onChange={(e) => updateTransaction(transaction.row_id, 'Ref1', e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </Td>
        <Td>
          <Input
            size="sm"
            value={transaction.Ref2}
            onChange={(e) => updateTransaction(transaction.row_id, 'Ref2', e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('labels.reference2')}
          />
        </Td>
        <Td>
          <Input
            size="sm"
            value={transaction.Administration}
            isReadOnly
            bg="gray.100"
            cursor="not-allowed"
            title={t('labels.administrationAutoSet')}
          />
        </Td>
        <Td></Td>
        <Td></Td>
      </Tr>
    </React.Fragment>
  );
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const BankingProcessorTable: React.FC<BankingProcessorTableProps> = ({
  transactions,
  chartAccounts,
  loading,
  patternResults,
  updateTransaction,
  onApplyPatterns,
  onSaveTransactions,
  getPatternFieldStyle,
  t,
}) => {
  if (transactions.length === 0) return null;

  return (
    <>
      {/* Pattern Application Results */}
      {patternResults && (
        <PatternResultsCard patternResults={patternResults} t={t} />
      )}

      {/* Transaction Review Table */}
      <Box mb={6}>
        <HStack justify="space-between" mb={4}>
          <Heading size="md">{t('fileProcessing.reviewTransactions', { count: transactions.length })}</Heading>
          <HStack>
            <Button
              colorScheme="blue"
              isLoading={loading}
              onClick={onApplyPatterns}
              loadingText={t('fileProcessing.applyingPatterns')}
            >
              {t('fileProcessing.applyPatterns')}
            </Button>
            <FieldHelp
              tooltip="Automatically assigns debit/credit accounts based on your historical transaction patterns"
              docsSection="banking/pattern-matching"
            />
            <Button
              type="submit"
              colorScheme="green"
              isLoading={loading}
              onClick={onSaveTransactions}
              loadingText={t('fileProcessing.saving')}
            >
              {t('fileProcessing.saveTransactions')}
            </Button>
          </HStack>
        </HStack>

        <Box overflowX="auto" maxH="600px">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th>{t('labels.trxNumber')}</Th>
                <Th>{t('labels.date')}</Th>
                <Th>{t('table.description')}</Th>
                <Th>{t('table.amount')}</Th>
                <Th>{t('table.debit')}</Th>
                <Th>{t('table.credit')}</Th>
              </Tr>
              <Tr>
                <Th>{t('labels.refNumber')}</Th>
                <Th>{t('table.ref1')}</Th>
                <Th>{t('table.ref2')}</Th>
                <Th>{t('labels.administration')}</Th>
                <Th colSpan={2}></Th>
              </Tr>
            </Thead>
            <Tbody>
              {transactions.map((transaction, index) => (
                <TransactionRow
                  key={transaction.row_id}
                  transaction={transaction}
                  index={index}
                  chartAccounts={chartAccounts}
                  updateTransaction={updateTransaction}
                  getPatternFieldStyle={getPatternFieldStyle}
                  t={t}
                />
              ))}
            </Tbody>
          </Table>
        </Box>
      </Box>
    </>
  );
};

export default BankingProcessorTable;
