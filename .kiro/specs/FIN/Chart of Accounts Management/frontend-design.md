# Chart of Accounts Management - Frontend Design

**Status**: Draft  
**Date**: 2026-02-17  
**Module**: Financial (FIN) - Tenant Admin  
**Related**: proposal.md, backend-design.md

## Table of Contents

1. [Component Architecture](#component-architecture)
2. [Main Component: ChartOfAccounts](#main-component-chartofaccounts)
3. [Modal Component: AccountModal](#modal-component-accountmodal)
4. [State Management](#state-management)
5. [API Integration](#api-integration)
6. [UI/UX Design](#uiux-design)
7. [Routing & Navigation](#routing--navigation)
8. [Testing Strategy](#testing-strategy)

---

## Component Architecture

### Component Hierarchy

```
TenantAdmin (existing)
└── ChartOfAccounts.tsx (new)
    ├── FilterPanel (from generic filter framework)
    │   └── GenericFilter (search input)
    ├── Table (Chakra UI)
    │   ├── Thead
    │   ├── Tbody
    │   └── Tr (clickable rows)
    └── AccountModal.tsx (new)
        ├── Modal (Chakra UI)
        ├── ModalOverlay
        ├── ModalContent
        │   ├── ModalHeader
        │   ├── ModalCloseButton
        │   └── ModalBody
        │       ├── FormControl (Account)
        │       ├── FormControl (Name)
        │       ├── FormControl (Lookup)
        │       ├── FormControl (Tax Category)
        │       └── ButtonGroup (Save/Cancel/Delete)
        └── DeleteConfirmDialog (Chakra UI AlertDialog)
```

### File Structure

```
frontend/src/
├── pages/
│   └── TenantAdmin/
│       ├── ChartOfAccounts.tsx (main component)
│       └── AccountModal.tsx (add/edit modal)
├── services/
│   └── chartOfAccountsService.ts (API calls)
├── types/
│   └── chartOfAccounts.ts (TypeScript interfaces)
└── components/
    └── filters/
        ├── GenericFilter.tsx (existing)
        └── FilterPanel.tsx (existing)
```

---

## Main Component: ChartOfAccounts

### TypeScript Interfaces

**File**: `frontend/src/types/chartOfAccounts.ts`

```typescript
export interface Account {
  account: string;
  accountName: string;
  accountLookup: string;
  belastingaangifte: string;
}

export interface AccountsResponse {
  success: boolean;
  accounts: Account[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  account: Account | null;
  mode: "create" | "edit";
  onSave: (account: Account) => Promise<void>;
  onDelete?: (accountNumber: string) => Promise<void>;
}
```

### Component Implementation

**File**: `frontend/src/pages/TenantAdmin/ChartOfAccounts.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import {
  Box,
  VStack,
  HStack,
  Button,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Text,
  useToast,
  useDisclosure,
  Spinner,
  Center,
  Alert,
  AlertIcon,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { GenericFilter } from '../../components/filters/GenericFilter';
import { FilterPanel } from '../../components/filters/FilterPanel';
import { AccountModal } from './AccountModal';
import { chartOfAccountsService } from '../../services/chartOfAccountsService';
import { Account } from '../../types/chartOfAccounts';
import { getTenantModules } from '../../services/apiService';

const ChartOfAccounts: React.FC = () => {
  // State
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [filteredAccounts, setFilteredAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [hasFIN, setHasFIN] = useState(false);

  // Hooks
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  // Check FIN module access
  useEffect(() => {
    const checkModuleAccess = async () => {
      try {
        const { available_modules } = await getTenantModules();
        setHasFIN(available_modules.includes('FIN'));
      } catch (error) {
        console.error('Error checking module access:', error);
      }
    };
    checkModuleAccess();
  }, []);

  // Load accounts
  useEffect(() => {
    if (hasFIN) {
      loadAccounts();
    }
  }, [hasFIN]);

  // Filter accounts when search changes
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredAccounts(accounts);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = accounts.filter(
        (acc) =>
          acc.account.toLowerCase().includes(query) ||
          acc.accountName.toLowerCase().includes(query)
      );
      setFilteredAccounts(filtered);
    }
  }, [searchQuery, accounts]);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const response = await chartOfAccountsService.listAccounts();
      setAccounts(response.accounts);
      setFilteredAccounts(response.accounts);
    } catch (error) {
      toast({
        title: 'Error loading accounts',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRowClick = (account: Account) => {
    setSelectedAccount(account);
    setModalMode('edit');
    onOpen();
  };

  const handleAddClick = () => {
    setSelectedAccount(null);
    setModalMode('create');
    onOpen();
  };

  const handleSave = async (account: Account) => {
    try {
      if (modalMode === 'create') {
        await chartOfAccountsService.createAccount(account);
        toast({
          title: 'Account created',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
      } else {
        await chartOfAccountsService.updateAccount(account.account, account);
        toast({
          title: 'Account updated',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
      }
      await loadAccounts();
      onClose();
    } catch (error) {
      toast({
        title: modalMode === 'create' ? 'Error creating account' : 'Error updating account',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleDelete = async (accountNumber: string) => {
    try {
      await chartOfAccountsService.deleteAccount(accountNumber);
      toast({
        title: 'Account deleted',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
      await loadAccounts();
      onClose();
    } catch (error) {
      toast({
        title: 'Error deleting account',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  // Module access check
  if (!hasFIN) {
    return (
      <Box p={6}>
        <Alert status="warning">
          <AlertIcon />
          FIN module is not enabled for this tenant. Contact your administrator.
        </Alert>
      </Box>
    );
  }

  // Loading state
  if (loading) {
    return (
      <Center h="400px">
        <Spinner size="xl" />
      </Center>
    );
  }

  return (
    <Box p={6}>
      <VStack spacing={6} align="stretch">
        {/* Header */}
        <HStack justify="space-between">
          <Text fontSize="2xl" fontWeight="bold">
            Chart of Accounts
          </Text>
          <Button
            leftIcon={<AddIcon />}
            colorScheme="blue"
            onClick={handleAddClick}
          >
            Add Account
          </Button>
        </HStack>

        {/* Filter Panel */}
        <FilterPanel>
          <GenericFilter
            placeholder="Search by account number or name..."
            value={searchQuery}
            onChange={setSearchQuery}
          />
        </FilterPanel>

        {/* Results Summary */}
        <Text fontSize="sm" color="gray.600">
          Showing {filteredAccounts.length} of {accounts.length} accounts
        </Text>

        {/* Table */}
        <Box borderWidth={1} borderRadius="md" overflow="hidden">
          <Table variant="simple">
            <Thead bg="gray.50">
              <Tr>
                <Th>Account</Th>
                <Th>Name</Th>
                <Th>Lookup</Th>
                <Th>Tax Category</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filteredAccounts.map((account) => (
                <Tr
                  key={account.account}
                  onClick={() => handleRowClick(account)}
                  cursor="pointer"
                  _hover={{ bg: 'gray.50' }}
                  transition="background 0.2s"
                >
                  <Td fontWeight="medium">{account.account}</Td>
                  <Td>{account.accountName}</Td>
                  <Td>{account.accountLookup}</Td>
                  <Td>{account.belastingaangifte}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>

        {/* Empty State */}
        {filteredAccounts.length === 0 && (
          <Center py={10}>
            <VStack spacing={3}>
              <Text fontSize="lg" color="gray.500">
                {searchQuery ? 'No accounts match your search' : 'No accounts found'}
              </Text>
              {searchQuery && (
                <Button size="sm" onClick={() => setSearchQuery('')}>
                  Clear search
                </Button>
              )}
            </VStack>
          </Center>
        )}

        {/* Modal */}
        <AccountModal
          isOpen={isOpen}
          onClose={onClose}
          account={selectedAccount}
          mode={modalMode}
          onSave={handleSave}
          onDelete={modalMode === 'edit' ? handleDelete : undefined}
        />
      </VStack>
    </Box>
  );
};

export default ChartOfAccounts;
```

---

## Modal Component: AccountModal

**File**: `frontend/src/pages/TenantAdmin/AccountModal.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  FormControl,
  FormLabel,
  Input,
  Button,
  VStack,
  HStack,
  useDisclosure,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  FormErrorMessage,
} from '@chakra-ui/react';
import { Account, AccountModalProps } from '../../types/chartOfAccounts';

export const AccountModal: React.FC<AccountModalProps> = ({
  isOpen,
  onClose,
  account,
  mode,
  onSave,
  onDelete,
}) => {
  // Form state
  const [formData, setFormData] = useState<Account>({
    account: '',
    accountName: '',
    accountLookup: '',
    belastingaangifte: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Delete confirmation dialog
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  // Initialize form data
  useEffect(() => {
    if (account && mode === 'edit') {
      setFormData(account);
    } else {
      setFormData({
        account: '',
        accountName: '',
        accountLookup: '',
        belastingaangifte: '',
      });
    }
    setErrors({});
  }, [account, mode, isOpen]);

  // Validation
  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.account.trim()) {
      newErrors.account = 'Account number is required';
    }
    if (!formData.accountName.trim()) {
      newErrors.accountName = 'Account name is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle input change
  const handleChange = (field: keyof Account, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    // Clear error for this field
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  // Handle save
  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      await onSave(formData);
    } finally {
      setSaving(false);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    if (!onDelete || !account) return;

    setDeleting(true);
    try {
      await onDelete(account.account);
      onDeleteClose();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>
            {mode === 'create' ? 'Add Account' : 'Edit Account'}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody pb={6}>
            <VStack spacing={4}>
              {/* Account Number */}
              <FormControl isInvalid={!!errors.account} isRequired>
                <FormLabel>Account Number</FormLabel>
                <Input
                  value={formData.account}
                  onChange={(e) => handleChange('account', e.target.value)}
                  placeholder="e.g., 1000"
                  isDisabled={mode === 'edit'} // Cannot change account number
                />
                <FormErrorMessage>{errors.account}</FormErrorMessage>
              </FormControl>

              {/* Account Name */}
              <FormControl isInvalid={!!errors.accountName} isRequired>
                <FormLabel>Account Name</FormLabel>
                <Input
                  value={formData.accountName}
                  onChange={(e) => handleChange('accountName', e.target.value)}
                  placeholder="e.g., Kas"
                />
                <FormErrorMessage>{errors.accountName}</FormErrorMessage>
              </FormControl>

              {/* Account Lookup */}
              <FormControl>
                <FormLabel>Lookup Code</FormLabel>
                <Input
                  value={formData.accountLookup}
                  onChange={(e) => handleChange('accountLookup', e.target.value)}
                  placeholder="e.g., CASH"
                />
              </FormControl>

              {/* Tax Category */}
              <FormControl>
                <FormLabel>Tax Category</FormLabel>
                <Input
                  value={formData.belastingaangifte}
                  onChange={(e) =>
                    handleChange('belastingaangifte', e.target.value)
                  }
                  placeholder="e.g., Activa"
                />
              </FormControl>

              {/* Buttons */}
              <HStack spacing={3} width="100%" justify="space-between" pt={4}>
                {/* Delete button (left side, only in edit mode) */}
                {mode === 'edit' && onDelete && (
                  <Button
                    colorScheme="red"
                    variant="outline"
                    onClick={onDeleteOpen}
                  >
                    Delete
                  </Button>
                )}
                <Box flex={1} /> {/* Spacer */}

                {/* Save/Cancel buttons (right side) */}
                <HStack spacing={3}>
                  <Button variant="ghost" onClick={onClose}>
                    Cancel
                  </Button>
                  <Button
                    colorScheme="blue"
                    onClick={handleSave}
                    isLoading={saving}
                    loadingText="Saving..."
                  >
                    {mode === 'create' ? 'Create' : 'Save'}
                  </Button>
                </HStack>
              </HStack>
            </VStack>
          </ModalBody>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Account
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete account{' '}
              <strong>{account?.account}</strong>? This action cannot be undone.
              {mode === 'edit' && (
                <Box mt={2} fontSize="sm" color="gray.600">
                  Note: You cannot delete an account that is used in transactions.
                </Box>
              )}
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDelete}
                ml={3}
                isLoading={deleting}
                loadingText="Deleting..."
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
};
```

---

## State Management

### Component State

**ChartOfAccounts.tsx**:

- `accounts: Account[]` - All accounts from API
- `filteredAccounts: Account[]` - Filtered results based on search
- `loading: boolean` - Loading state for initial data fetch
- `searchQuery: string` - Current search query
- `selectedAccount: Account | null` - Account being edited
- `modalMode: 'create' | 'edit'` - Modal mode
- `hasFIN: boolean` - FIN module access check

**AccountModal.tsx**:

- `formData: Account` - Form field values
- `errors: Record<string, string>` - Validation errors
- `saving: boolean` - Save operation in progress
- `deleting: boolean` - Delete operation in progress

### Data Flow

```
1. Component Mount
   └── Check FIN module access
       └── Load accounts from API
           └── Set accounts and filteredAccounts state

2. User Types in Search
   └── Update searchQuery state
       └── Filter accounts locally
           └── Update filteredAccounts state

3. User Clicks Row
   └── Set selectedAccount
       └── Set modalMode to 'edit'
           └── Open modal

4. User Clicks Add Button
   └── Set selectedAccount to null
       └── Set modalMode to 'create'
           └── Open modal

5. User Saves in Modal
   └── Validate form
       └── Call API (create or update)
           └── Reload accounts
               └── Close modal

6. User Deletes in Modal
   └── Show confirmation dialog
       └── Call API (delete)
           └── Reload accounts
               └── Close modal
```

---

## API Integration

### Service Layer

**File**: `frontend/src/services/chartOfAccountsService.ts`

```typescript
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
} from "./apiService";
import { Account, AccountsResponse } from "../types/chartOfAccounts";

export const chartOfAccountsService = {
  /**
   * List all accounts for current tenant
   */
  async listAccounts(params?: {
    search?: string;
    page?: number;
    limit?: number;
  }): Promise<AccountsResponse> {
    const queryParams = new URLSearchParams();
    if (params?.search) queryParams.append("search", params.search);
    if (params?.page) queryParams.append("page", params.page.toString());
    if (params?.limit) queryParams.append("limit", params.limit.toString());

    const url = `/api/tenant-admin/chart-of-accounts${
      queryParams.toString() ? `?${queryParams.toString()}` : ""
    }`;

    const response = await authenticatedGet(url);
    return response.json();
  },

  /**
   * Get single account
   */
  async getAccount(accountNumber: string): Promise<Account> {
    const response = await authenticatedGet(
      `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`,
    );
    const data = await response.json();
    return data.account;
  },

  /**
   * Create new account
   */
  async createAccount(account: Account): Promise<Account> {
    const response = await authenticatedPost(
      "/api/tenant-admin/chart-of-accounts",
      account,
    );
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || "Failed to create account");
    }

    return data.account;
  },

  /**
   * Update existing account
   */
  async updateAccount(
    accountNumber: string,
    account: Partial<Account>,
  ): Promise<Account> {
    const response = await authenticatedPut(
      `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`,
      account,
    );
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || "Failed to update account");
    }

    return data.account;
  },

  /**
   * Delete account
   */
  async deleteAccount(accountNumber: string): Promise<void> {
    const response = await authenticatedDelete(
      `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`,
    );
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || "Failed to delete account");
    }
  },

  /**
   * Export accounts to Excel
   */
  async exportAccounts(): Promise<Blob> {
    const response = await authenticatedGet(
      "/api/tenant-admin/chart-of-accounts/export",
    );
    return response.blob();
  },

  /**
   * Import accounts from Excel
   */
  async importAccounts(file: File): Promise<{
    imported: number;
    updated: number;
    total: number;
  }> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/tenant-admin/chart-of-accounts/import", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${localStorage.getItem("token")}`,
        "X-Tenant": localStorage.getItem("currentTenant") || "",
      },
      body: formData,
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || "Failed to import accounts");
    }

    return {
      imported: data.imported,
      updated: data.updated,
      total: data.total,
    };
  },
};
```

### Error Handling

```typescript
// In component
try {
  await chartOfAccountsService.createAccount(account);
  toast({ title: "Success", status: "success" });
} catch (error) {
  if (error instanceof Error) {
    // Parse error message
    const message = error.message;

    // Handle specific errors
    if (message.includes("already exists")) {
      toast({
        title: "Account already exists",
        description: "Please use a different account number",
        status: "error",
      });
    } else if (message.includes("FIN module not enabled")) {
      toast({
        title: "Access Denied",
        description: "FIN module is not enabled for this tenant",
        status: "error",
      });
    } else {
      toast({
        title: "Error",
        description: message,
        status: "error",
      });
    }
  }
}
```
