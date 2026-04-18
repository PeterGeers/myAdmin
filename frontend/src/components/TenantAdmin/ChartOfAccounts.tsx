/**
 * Chart of Accounts Management Component
 * 
 * Allows tenant admins to view, create, edit, delete, import, and export
 * accounts from the chart of accounts (rekeningschema).
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useTableConfig('chart_of_accounts') for parameter-driven column/filter config
 * - useFilterableTable for combined filtering + sorting
 * - FilterableHeader for inline column text filters with sort indicators
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Button,
  HStack,
  VStack,
  Table,
  Thead,
  Tbody,
  Tr,
  Td,
  Spinner,
  Text,
  useToast,
  useDisclosure,
  Alert,
  AlertIcon
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, AttachmentIcon } from '@chakra-ui/icons';
import {
  listAccounts,
  exportAccounts,
  importAccounts,
  createAccount,
  updateAccount,
  deleteAccount
} from '../../services/chartOfAccountsService';
import { Account, AccountFormData } from '../../types/chartOfAccounts';
import AccountModal from './AccountModal';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { useTableConfig } from '../../hooks/useTableConfig';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

interface ChartOfAccountsProps {
  tenant: string;
}

/**
 * Map column keys (from useTableConfig) to translation-based display labels.
 * Falls back to the raw key if no label is defined.
 */
function useColumnLabels() {
  const { t } = useTypedTranslation('admin');
  return useMemo<Record<string, string>>(() => ({
    Account: t('chartOfAccounts.table.account'),
    AccountName: t('chartOfAccounts.table.name'),
    AccountLookup: t('chartOfAccounts.table.lookup'),
    SubParent: t('chartOfAccounts.table.subParent'),
    Parent: t('chartOfAccounts.table.parent'),
    VW: t('chartOfAccounts.table.vw'),
    Belastingaangifte: t('chartOfAccounts.table.taxCategory'),
    parameters: 'Parameters',
  }), [t]);
}

const ChartOfAccounts: React.FC<ChartOfAccountsProps> = ({ tenant }) => {
  const { t } = useTypedTranslation('admin');
  const columnLabels = useColumnLabels();

  // State
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [hasFIN, setHasFIN] = useState(true);

  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  // Parameter-driven table configuration
  const tableConfig = useTableConfig('chart_of_accounts');

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
  } = useFilterableTable<Account>(accounts, {
    initialFilters,
    defaultSort: tableConfig.defaultSort,
  });

  // Load accounts
  const loadAccounts = async () => {
    setLoading(true);
    try {
      // Request all accounts (limit=1000 is the max allowed by backend)
      const response = await listAccounts({ limit: 1000 });
      setAccounts(response.accounts);
    } catch (error) {
      // Check if it's a FIN module error
      if (error instanceof Error && error.message.includes('FIN module')) {
        setHasFIN(false);
      } else {
        toast({
          title: t('chartOfAccounts.messages.errorLoading'),
          description: error instanceof Error ? error.message : t('chartOfAccounts.messages.unknownError'),
          status: 'error',
          duration: 5000,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tenant) {
      loadAccounts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  // Handlers
  const handleAddClick = () => {
    setSelectedAccount(null);
    setModalMode('create');
    onOpen();
  };

  const handleRowClick = (account: Account) => {
    setSelectedAccount(account);
    setModalMode('edit');
    onOpen();
  };

  const handleSave = async (accountData: AccountFormData) => {
    try {
      if (modalMode === 'create') {
        await createAccount(accountData);
        toast({
          title: t('chartOfAccounts.messages.accountCreated'),
          status: 'success',
          duration: 3000,
        });
      } else if (selectedAccount) {
        await updateAccount(selectedAccount.Account, accountData);
        toast({
          title: t('chartOfAccounts.messages.accountUpdated'),
          status: 'success',
          duration: 3000,
        });
      }
      onClose();
      loadAccounts();
    } catch (error) {
      toast({
        title: modalMode === 'create' ? t('chartOfAccounts.messages.errorCreating') : t('chartOfAccounts.messages.errorUpdating'),
        description: error instanceof Error ? error.message : t('chartOfAccounts.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
      throw error; // Re-throw so modal can handle it
    }
  };

  const handleDelete = async (accountNumber: string) => {
    try {
      await deleteAccount(accountNumber);
      toast({
        title: t('chartOfAccounts.messages.accountDeleted'),
        status: 'success',
        duration: 3000,
      });
      onClose();
      loadAccounts();
    } catch (error) {
      toast({
        title: t('chartOfAccounts.messages.errorDeleting'),
        description: error instanceof Error ? error.message : t('chartOfAccounts.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
      throw error; // Re-throw so modal can handle it
    }
  };

  const handleExport = async () => {
    try {
      const blob = await exportAccounts();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chart_of_accounts_${tenant}_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      toast({
        title: t('chartOfAccounts.messages.exportSuccessful'),
        description: t('chartOfAccounts.messages.exportDescription'),
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      toast({
        title: t('chartOfAccounts.messages.errorExporting'),
        description: error instanceof Error ? error.message : t('chartOfAccounts.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const result = await importAccounts(file);
      
      if ('errors' in result) {
        // Validation errors
        toast({
          title: t('chartOfAccounts.messages.importValidationErrors'),
          description: t('chartOfAccounts.messages.importErrorsDescription', { count: result.errors.length }),
          status: 'warning',
          duration: 5000,
        });
        console.error('Import errors:', result.errors);
      } else {
        // Success
        toast({
          title: t('chartOfAccounts.messages.importSuccessful'),
          description: t('chartOfAccounts.messages.importDescription', { imported: result.imported, updated: result.updated }),
          status: 'success',
          duration: 5000,
        });
        loadAccounts();
      }
    } catch (error) {
      toast({
        title: t('chartOfAccounts.messages.errorImporting'),
        description: error instanceof Error ? error.message : t('chartOfAccounts.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    }
    
    // Reset file input
    event.target.value = '';
  };

  // Render cell value with column-specific styling
  const renderCellValue = (account: Account, col: string) => {
    const value = account[col as keyof Account];
    switch (col) {
      case 'Account':
        return (
          <Td color="orange.400" fontWeight="medium">
            {value}
          </Td>
        );
      case 'AccountName':
        return <Td color="white">{value}</Td>;
      case 'parameters':
        return (
          <Td color="gray.300" fontSize="xs" maxW="200px" title={String(value || '')}>
            {value
              ? (String(value).length > 30
                  ? String(value).substring(0, 30) + '...'
                  : String(value))
              : '-'}
          </Td>
        );
      default:
        return <Td color="gray.300">{value || '-'}</Td>;
    }
  };

  // Show alert if FIN module not enabled
  if (!hasFIN) {
    return (
      <Alert status="warning">
        <AlertIcon />
        {t('chartOfAccounts.messages.finModuleNotEnabled')}
      </Alert>
    );
  }

  // Loading state
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* Header with actions and results summary */}
      <HStack justify="space-between" wrap="wrap">
        <Text color="gray.400" fontSize="sm">
          {t('chartOfAccounts.showingResults', { filtered: processedData.length, total: accounts.length })}
        </Text>
        <HStack spacing={2}>
          <Button
            leftIcon={<DownloadIcon />}
            colorScheme="orange"
            onClick={handleExport}
            size="sm"
          >
            {t('chartOfAccounts.export')}
          </Button>
          <Button
            as="label"
            leftIcon={<AttachmentIcon />}
            colorScheme="orange"
            size="sm"
            cursor="pointer"
          >
            {t('chartOfAccounts.import')}
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={handleImport}
              style={{ display: 'none' }}
            />
          </Button>
          <Button
            leftIcon={<AddIcon />}
            colorScheme="orange"
            onClick={handleAddClick}
            size="sm"
          >
            {t('chartOfAccounts.addAccount')}
          </Button>
        </HStack>
      </HStack>

      {/* Clear filters button */}
      {hasActiveFilters && (
        <Button
          variant="link"
          colorScheme="orange"
          onClick={resetFilters}
          size="sm"
        >
          {t('chartOfAccounts.clearAllFilters')}
        </Button>
      )}

      {/* Accounts table */}
      <Box overflowX="auto" bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              {tableConfig.columns.map((col) => {
                const isFilterable = tableConfig.filterableColumns.includes(col);
                return (
                  <FilterableHeader
                    key={col}
                    label={columnLabels[col] || col}
                    filterValue={isFilterable ? filters[col] : undefined}
                    onFilterChange={isFilterable ? (v) => setFilter(col, v) : undefined}
                    sortable
                    sortDirection={sortField === col ? sortDirection : null}
                    onSort={() => handleSort(col)}
                  />
                );
              })}
            </Tr>
          </Thead>
          <Tbody>
            {processedData.map((account) => (
              <Tr
                key={account.Account}
                onClick={() => handleRowClick(account)}
                cursor="pointer"
                _hover={{ bg: 'gray.700' }}
                transition="background 0.2s"
              >
                {tableConfig.columns.map((col) => (
                  <React.Fragment key={col}>
                    {renderCellValue(account, col)}
                  </React.Fragment>
                ))}
              </Tr>
            ))}
          </Tbody>
        </Table>

        {/* Empty state */}
        {processedData.length === 0 && (
          <Box textAlign="center" py={8}>
            <Text color="gray.400">
              {hasActiveFilters ? t('chartOfAccounts.emptyState.noMatches') : t('chartOfAccounts.emptyState.noAccounts')}
            </Text>
            {hasActiveFilters && (
              <Button
                variant="link"
                colorScheme="orange"
                onClick={resetFilters}
                mt={2}
              >
                {t('chartOfAccounts.clearFilters')}
              </Button>
            )}
          </Box>
        )}
      </Box>

      {/* Account Modal */}
      <AccountModal
        isOpen={isOpen}
        onClose={onClose}
        account={selectedAccount}
        mode={modalMode}
        onSave={handleSave}
        onDelete={handleDelete}
      />
    </VStack>
  );
};

export default ChartOfAccounts;
