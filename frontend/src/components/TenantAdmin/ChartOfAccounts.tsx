/**
 * Chart of Accounts Management Component
 * 
 * Allows tenant admins to view, create, edit, delete, import, and export
 * accounts from the chart of accounts (rekeningschema).
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  HStack,
  VStack,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
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
import { FilterPanel } from '../filters/FilterPanel';
import { SearchFilterConfig } from '../filters/types';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

interface ChartOfAccountsProps {
  tenant: string;
}

const ChartOfAccounts: React.FC<ChartOfAccountsProps> = ({ tenant }) => {
  const { t } = useTypedTranslation('admin');
  // State
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [filteredAccounts, setFilteredAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [hasFIN, setHasFIN] = useState(true);
  
  // Search filters - separate field for each column
  const [searchFilters, setSearchFilters] = useState({
    Account: '',
    AccountName: '',
    AccountLookup: '',
    SubParent: '',
    Parent: '',
    VW: '',
    Belastingaangifte: ''
  });
  
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  // Load accounts
  const loadAccounts = async () => {
    setLoading(true);
    try {
      // Request all accounts (limit=1000 is the max allowed by backend)
      const response = await listAccounts({ limit: 1000 });
      setAccounts(response.accounts);
      setFilteredAccounts(response.accounts);
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

  // Filter accounts when search filters change
  useEffect(() => {
    const filtered = accounts.filter((acc) => {
      return Object.entries(searchFilters).every(([key, value]) => {
        if (!value) return true;
        const fieldValue = acc[key as keyof Account]?.toString().toLowerCase() || '';
        return fieldValue.includes(value.toLowerCase());
      });
    });
    setFilteredAccounts(filtered);
  }, [searchFilters, accounts]);

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
          {t('chartOfAccounts.showingResults', { filtered: filteredAccounts.length, total: accounts.length })}
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

      {/* Search Filters using FilterPanel framework */}
      <FilterPanel
        layout="horizontal"
        size="sm"
        spacing={2}
        labelColor="gray.300"
        bg="gray.800"
        color="white"
        filters={[
          {
            type: 'search',
            label: t('chartOfAccounts.filters.accountNumber'),
            value: searchFilters.Account,
            onChange: (value) => setSearchFilters(prev => ({...prev, Account: value})),
            placeholder: t('chartOfAccounts.filters.accountNumberPlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.accountName'),
            value: searchFilters.AccountName,
            onChange: (value) => setSearchFilters(prev => ({...prev, AccountName: value})),
            placeholder: t('chartOfAccounts.filters.accountNamePlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.lookupCode'),
            value: searchFilters.AccountLookup,
            onChange: (value) => setSearchFilters(prev => ({...prev, AccountLookup: value})),
            placeholder: t('chartOfAccounts.filters.lookupCodePlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.subParent'),
            value: searchFilters.SubParent,
            onChange: (value) => setSearchFilters(prev => ({...prev, SubParent: value})),
            placeholder: t('chartOfAccounts.filters.subParentPlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.parent'),
            value: searchFilters.Parent,
            onChange: (value) => setSearchFilters(prev => ({...prev, Parent: value})),
            placeholder: t('chartOfAccounts.filters.parentPlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.vw'),
            value: searchFilters.VW,
            onChange: (value) => setSearchFilters(prev => ({...prev, VW: value})),
            placeholder: t('chartOfAccounts.filters.vwPlaceholder')
          } as SearchFilterConfig,
          {
            type: 'search',
            label: t('chartOfAccounts.filters.taxCategory'),
            value: searchFilters.Belastingaangifte,
            onChange: (value) => setSearchFilters(prev => ({...prev, Belastingaangifte: value})),
            placeholder: t('chartOfAccounts.filters.taxCategoryPlaceholder')
          } as SearchFilterConfig
        ]}
      />
      
      {/* Clear filters button */}
      {Object.values(searchFilters).some(v => v) && (
        <Button
          variant="link"
          colorScheme="orange"
          onClick={() => setSearchFilters({
            Account: '',
            AccountName: '',
            AccountLookup: '',
            SubParent: '',
            Parent: '',
            VW: '',
            Belastingaangifte: ''
          })}
          size="sm"
        >
          {t('chartOfAccounts.clearAllFilters')}
        </Button>
      )}

      {/* Accounts table */}
      <Box overflowX="auto" bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
        <Table variant="simple" size="sm">
          <Thead bg="gray.700">
            <Tr>
              <Th color="gray.300">{t('chartOfAccounts.table.account')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.name')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.lookup')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.subParent')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.parent')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.vw')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.taxCategory')}</Th>
              <Th color="gray.300">{t('chartOfAccounts.table.pattern')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {filteredAccounts.map((account) => (
              <Tr
                key={account.Account}
                onClick={() => handleRowClick(account)}
                cursor="pointer"
                _hover={{ bg: 'gray.700' }}
                transition="background 0.2s"
              >
                <Td color="orange.400" fontWeight="medium">
                  {account.Account}
                </Td>
                <Td color="white">{account.AccountName}</Td>
                <Td color="gray.300">{account.AccountLookup}</Td>
                <Td color="gray.300">{account.SubParent || '-'}</Td>
                <Td color="gray.300">{account.Parent || '-'}</Td>
                <Td color="gray.300">{account.VW || '-'}</Td>
                <Td color="gray.300">{account.Belastingaangifte}</Td>
                <Td color="gray.300">{account.Pattern ? '✓' : ''}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>

        {/* Empty state */}
        {filteredAccounts.length === 0 && (
          <Box textAlign="center" py={8}>
            <Text color="gray.400">
              {Object.values(searchFilters).some(v => v) ? t('chartOfAccounts.emptyState.noMatches') : t('chartOfAccounts.emptyState.noAccounts')}
            </Text>
            {Object.values(searchFilters).some(v => v) && (
              <Button
                variant="link"
                colorScheme="orange"
                onClick={() => setSearchFilters({
                  Account: '',
                  AccountName: '',
                  AccountLookup: '',
                  SubParent: '',
                  Parent: '',
                  VW: '',
                  Belastingaangifte: ''
                })}
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
