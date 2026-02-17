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

interface ChartOfAccountsProps {
  tenant: string;
}

const ChartOfAccounts: React.FC<ChartOfAccountsProps> = ({ tenant }) => {
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
          title: 'Error loading accounts',
          description: error instanceof Error ? error.message : 'Unknown error',
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
          title: 'Account created',
          status: 'success',
          duration: 3000,
        });
      } else if (selectedAccount) {
        await updateAccount(selectedAccount.Account, accountData);
        toast({
          title: 'Account updated',
          status: 'success',
          duration: 3000,
        });
      }
      onClose();
      loadAccounts();
    } catch (error) {
      toast({
        title: modalMode === 'create' ? 'Error creating account' : 'Error updating account',
        description: error instanceof Error ? error.message : 'Unknown error',
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
        title: 'Account deleted',
        status: 'success',
        duration: 3000,
      });
      onClose();
      loadAccounts();
    } catch (error) {
      toast({
        title: 'Error deleting account',
        description: error instanceof Error ? error.message : 'Unknown error',
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
        title: 'Export successful',
        description: 'Accounts exported to Excel',
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      toast({
        title: 'Error exporting accounts',
        description: error instanceof Error ? error.message : 'Unknown error',
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
          title: 'Import validation errors',
          description: `${result.errors.length} errors found. Check console for details.`,
          status: 'warning',
          duration: 5000,
        });
        console.error('Import errors:', result.errors);
      } else {
        // Success
        toast({
          title: 'Import successful',
          description: `Imported ${result.imported} new accounts, updated ${result.updated} existing accounts`,
          status: 'success',
          duration: 5000,
        });
        loadAccounts();
      }
    } catch (error) {
      toast({
        title: 'Error importing accounts',
        description: error instanceof Error ? error.message : 'Unknown error',
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
        FIN module not enabled for this tenant
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
          Showing {filteredAccounts.length} of {accounts.length} accounts
        </Text>
        <HStack spacing={2}>
          <Button
            leftIcon={<DownloadIcon />}
            colorScheme="orange"
            onClick={handleExport}
            size="sm"
          >
            Export
          </Button>
          <Button
            as="label"
            leftIcon={<AttachmentIcon />}
            colorScheme="orange"
            size="sm"
            cursor="pointer"
          >
            Import
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
            Add Account
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
            label: 'Account Number',
            value: searchFilters.Account,
            onChange: (value) => setSearchFilters(prev => ({...prev, Account: value})),
            placeholder: 'Search account number...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'Account Name',
            value: searchFilters.AccountName,
            onChange: (value) => setSearchFilters(prev => ({...prev, AccountName: value})),
            placeholder: 'Search account name...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'Lookup Code',
            value: searchFilters.AccountLookup,
            onChange: (value) => setSearchFilters(prev => ({...prev, AccountLookup: value})),
            placeholder: 'Search lookup code...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'Sub Parent',
            value: searchFilters.SubParent,
            onChange: (value) => setSearchFilters(prev => ({...prev, SubParent: value})),
            placeholder: 'Search sub parent...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'Parent',
            value: searchFilters.Parent,
            onChange: (value) => setSearchFilters(prev => ({...prev, Parent: value})),
            placeholder: 'Search parent...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'VW',
            value: searchFilters.VW,
            onChange: (value) => setSearchFilters(prev => ({...prev, VW: value})),
            placeholder: 'Search VW...'
          } as SearchFilterConfig,
          {
            type: 'search',
            label: 'Tax Category',
            value: searchFilters.Belastingaangifte,
            onChange: (value) => setSearchFilters(prev => ({...prev, Belastingaangifte: value})),
            placeholder: 'Search tax category...'
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
          Clear All Filters
        </Button>
      )}

      {/* Accounts table */}
      <Box overflowX="auto" bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
        <Table variant="simple" size="sm">
          <Thead bg="gray.700">
            <Tr>
              <Th color="gray.300">Account</Th>
              <Th color="gray.300">Name</Th>
              <Th color="gray.300">Lookup</Th>
              <Th color="gray.300">Sub Parent</Th>
              <Th color="gray.300">Parent</Th>
              <Th color="gray.300">VW</Th>
              <Th color="gray.300">Tax Category</Th>
              <Th color="gray.300">Pattern</Th>
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
              {Object.values(searchFilters).some(v => v) ? 'No accounts match your search' : 'No accounts found'}
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
                Clear filters
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
