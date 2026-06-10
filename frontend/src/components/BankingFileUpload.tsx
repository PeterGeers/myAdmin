/**
 * BankingFileUpload Component
 *
 * Extracted from BankingProcessor — handles CSV/TSV bank statement file selection,
 * validation, and processing initiation. Supports Rabobank CSV, Revolut TSV/CSV,
 * and credit card statement files.
 *
 * Features:
 * - File input accepting .csv and .tsv files (multiple selection)
 * - Selected file list with size display
 * - Process and Clear action buttons
 * - Status message display (success/error)
 * - Tenant IBAN validation before processing
 * - Duplicate detection via sequence number checks
 *
 * @module BankingFileUpload
 */

import React, { useCallback, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Button,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Text,
  VStack,
} from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { processCreditCardTransactions } from './banking/CreditCardProcessor';
import type { Transaction, LookupData } from './BankingProcessor';
import { parseCSVRow, processRevolutTransaction, processRabobankTransaction } from './BankingProcessor';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BankingFileUploadProps {
  /** Current lookup data for bank accounts, credit cards, etc. */
  lookupData: LookupData;
  /** Callback to update lookup data if fetched during processing */
  setLookupData: (data: LookupData) => void;
  /** Whether the component is in test mode */
  testMode: boolean;
  /** Callback invoked with processed transactions after file processing completes */
  onTransactionsLoaded: (transactions: Transaction[]) => void;
  /** Callback to set the loading state in the parent */
  setLoading: (loading: boolean) => void;
  /** Whether the parent is currently loading */
  loading: boolean;
  /** Status message to display */
  message: string;
  /** Callback to set the status message */
  setMessage: (message: string) => void;
  /** Helper to map lookup data from backend format */
  mapLookupData: (data: any) => any;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BankingFileUpload: React.FC<BankingFileUploadProps> = ({
  lookupData,
  setLookupData,
  testMode,
  onTransactionsLoaded,
  setLoading,
  loading,
  message,
  setMessage,
  mapLookupData,
}) => {
  const { t } = useTypedTranslation('banking');
  const { currentTenant } = useTenant();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    const csvTsvFiles = files.filter(file =>
      file.name.toLowerCase().endsWith('.csv') ||
      file.name.toLowerCase().endsWith('.tsv')
    );
    setSelectedFiles(csvTsvFiles);
    setMessage(t('messages.filesSelected', { count: csvTsvFiles.length }));
  }, [t, setMessage]);

  const clearSelection = useCallback(() => {
    setSelectedFiles([]);
  }, []);

  const processFiles = useCallback(async () => {
    if (selectedFiles.length === 0) {
      setMessage(t('messages.selectFiles'));
      return;
    }

    try {
      setLoading(true);

      let currentLookupData = lookupData;
      if (lookupData.bank_accounts.length === 0) {
        const response = await authenticatedGet('/api/banking/lookups');
        const data = await response.json();
        if (data.success) {
          currentLookupData = mapLookupData(data);
          setLookupData(currentLookupData);
        }
      }

      // Get current tenant for validation
      const tenant = localStorage.getItem('selectedTenant');
      if (!tenant) {
        setMessage(t('messages.noTenantSelected'));
        setLoading(false);
        return;
      }

      // Validate IBANs in files belong to current tenant BEFORE processing
      for (const file of selectedFiles) {
        const text = await file.text();
        const allRows = text.split('\n').filter(row => row.trim());

        if (allRows.length > 1) {
          let iban = '';

          // Determine IBAN based on file type
          const isRevolutFile = file.name.toLowerCase().endsWith('.tsv') ||
                               file.name.toLowerCase().startsWith('account-statement');

          if (isRevolutFile) {
            // Revolut files - find Revolut account from tenant's bank accounts
            const revolutAccount = currentLookupData.bank_accounts.find(ba => ba.rekeningNummer.includes('REVO'));
            if (!revolutAccount) {
              setMessage('No Revolut bank account configured for this tenant. Please add it in Chart of Accounts with the bank_account flag.');
              setLoading(false);
              return;
            }
            iban = revolutAccount.rekeningNummer;
          } else {
            // Other CSV files - extract IBAN from first column
            const firstDataRow = allRows[1]; // Skip header
            const columns = parseCSVRow(firstDataRow);
            iban = columns[0] || '';
          }

          if (iban) {
            const isCreditCardFile = file.name.startsWith('CSV_CC_') || file.name.startsWith('RA_CC_');

            if (isCreditCardFile) {
              // Credit card files: look up IBAN in credit_card_accounts
              const ccLookup = currentLookupData.credit_card_accounts?.find(cc => cc.iban === iban);
              if (!ccLookup) {
                setMessage(t('messages.accessDenied', { iban, file: file.name }));
                setLoading(false);
                return;
              }
            } else {
              // Regular bank files: look up IBAN in bank_accounts
              const bankLookup = currentLookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
              if (!bankLookup) {
                setMessage(t('messages.accessDenied', { iban, file: file.name }));
                setLoading(false);
                return;
              }
            }
          }
        }
      }

      // Process files into transactions
      const allTransactions: Transaction[] = [];
      let transactionIndex = 0;

      for (const file of selectedFiles) {
        const text = await file.text();
        const allRows = text.split('\n').filter(row => row.trim());
        const headerRow = allRows[0];
        const rows = allRows.slice(1); // Skip header

        for (let i = 0; i < rows.length; i++) {
          const row = rows[i];
          const currentIndex = transactionIndex + i;
          const isRevolutFile = file.name.toLowerCase().endsWith('.tsv') ||
                               file.name.toLowerCase().startsWith('account-statement');

          const columns = isRevolutFile && file.name.toLowerCase().endsWith('.tsv')
            ? row.split('\t').map(col => col.trim())
            : parseCSVRow(row);

          if (isRevolutFile) {
            const header = file.name.toLowerCase().endsWith('.tsv')
              ? headerRow.split('\t').map(col => col.trim())
              : parseCSVRow(headerRow);
            const revolutTransactions = processRevolutTransaction(
              columns, currentIndex,
              currentLookupData.bank_accounts.find(ba => ba.rekeningNummer.includes('REVO')),
              file.name,
              header
            );
            allTransactions.push(...revolutTransactions);
          } else if (file.name.startsWith('CSV_CC_') || file.name.startsWith('RA_CC_')) {
            const ccResult = processCreditCardTransactions(columns, currentIndex, currentLookupData, file.name);
            allTransactions.push(...ccResult.transactions);
            if (ccResult.warnings.length > 0) {
              ccResult.warnings.forEach(w => console.warn('[CreditCard]', w));
              setMessage(ccResult.warnings.join('\n'));
            }
          } else {
            const rabobankTransaction = processRabobankTransaction(columns, currentIndex, currentLookupData, file.name);
            if (rabobankTransaction) allTransactions.push(rabobankTransaction);
          }
        }

        transactionIndex += rows.length;
      }

      // Check for duplicates
      const iban = allTransactions[0]?.Ref1;
      const sequences = allTransactions.map(t => t.Ref2).filter(Boolean);

      if (iban && sequences.length > 0) {
        const response = await authenticatedPost('/api/banking/check-sequences', {
          iban,
          sequences,
          test_mode: testMode
        });

        const checkResult = await response.json();

        if (checkResult.success && checkResult.duplicates.length > 0) {
          const filteredTransactions = allTransactions.filter(t => !checkResult.duplicates.includes(t.Ref2));
          onTransactionsLoaded(filteredTransactions);
          setMessage(t('messages.duplicatesFiltered', {
            new: filteredTransactions.length,
            duplicates: checkResult.duplicates.length
          }));
        } else {
          onTransactionsLoaded(allTransactions);
          setMessage(t('messages.transactionsLoaded', { count: allTransactions.length }));
        }
      } else {
        onTransactionsLoaded(allTransactions);
        setMessage(t('messages.transactionsLoaded', { count: allTransactions.length }));
      }
    } catch (error) {
      setMessage(t('messages.errorProcessing', { error: String(error) }));
    } finally {
      setLoading(false);
    }
  }, [selectedFiles, lookupData, testMode, t, setLoading, setMessage, onTransactionsLoaded, mapLookupData, setLookupData]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <VStack align="stretch" spacing={4}>
      {/* File Selection */}
      <VStack align="stretch" mb={2}>
        <HStack mb={2}>
          <FormLabel color="white" mb={0}>{t('fileProcessing.selectFiles')}</FormLabel>
        </HStack>
        <FormControl>
          <Input
            type="file"
            accept=".csv,.tsv"
            multiple
            onChange={handleFileSelect}
            bg="white"
            color="black"
          />
        </FormControl>

        {selectedFiles.length > 0 && (
          <VStack align="stretch" spacing={2}>
            <Text color="white">{t('fileProcessing.selectedFiles', { count: selectedFiles.length })}</Text>
            {selectedFiles.map((file, index) => (
              <Text key={index} fontSize="sm" color="gray.300">
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </Text>
            ))}
            <HStack>
              <Button
                onClick={processFiles}
                isLoading={loading}
                colorScheme="blue"
                loadingText={t('fileProcessing.processing')}
              >
                {t('fileProcessing.processFiles')}
              </Button>
              <Button onClick={clearSelection} size="sm">
                {t('common:actions.clear')}
              </Button>
            </HStack>
          </VStack>
        )}
      </VStack>

      {/* Message Display */}
      {message && (
        <Alert
          status={message.includes('Error') ? 'error' : 'success'}
          mb={2}
          bg={message.includes('Error') ? 'red.100' : 'green.100'}
          color="black"
          borderColor={message.includes('Error') ? 'red.300' : 'green.300'}
        >
          <AlertIcon color={message.includes('Error') ? 'red.600' : 'green.600'} />
          {message}
        </Alert>
      )}
    </VStack>
  );
};

export default BankingFileUpload;
