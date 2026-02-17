/**
 * Account Modal Component
 * 
 * Modal for creating and editing chart of accounts entries.
 * Handles validation and provides delete functionality for existing accounts.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Button,
  FormControl,
  FormLabel,
  Input,
  FormErrorMessage,
  VStack,
  HStack,
  Box,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  useDisclosure,
  Text
} from '@chakra-ui/react';
import { AccountModalProps, AccountFormData } from '../../types/chartOfAccounts';

const AccountModal: React.FC<AccountModalProps> = ({
  isOpen,
  onClose,
  account,
  mode,
  onSave,
  onDelete
}) => {
  // Form state
  const [formData, setFormData] = useState<AccountFormData>({
    account: '',
    accountName: '',
    accountLookup: '',
    subParent: '',
    parent: '',
    vw: '',
    belastingaangifte: '',
    pattern: false
  });
  
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  // Delete confirmation dialog
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Initialize form when modal opens or account changes
  useEffect(() => {
    if (isOpen) {
      if (mode === 'edit' && account) {
        setFormData({
          account: account.Account,
          accountName: account.AccountName,
          accountLookup: account.AccountLookup || '',
          subParent: account.SubParent || '',
          parent: account.Parent || '',
          vw: account.VW || '',
          belastingaangifte: account.Belastingaangifte || '',
          pattern: !!account.Pattern
        });
      } else {
        setFormData({
          account: '',
          accountName: '',
          accountLookup: '',
          subParent: '',
          parent: '',
          vw: '',
          belastingaangifte: '',
          pattern: false
        });
      }
      setErrors({});
    }
  }, [isOpen, mode, account]);

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

  // Handlers
  const handleChange = (field: keyof AccountFormData, value: string) => {
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

  const handleSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      await onSave(formData);
      // onClose will be called by parent after successful save
    } catch (error) {
      // Error toast will be shown by parent
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete || !account) return;

    setDeleting(true);
    try {
      await onDelete(account.Account);
      onDeleteClose();
      // onClose will be called by parent after successful delete
    } catch (error) {
      // Error toast will be shown by parent
      onDeleteClose();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="orange.400">
            {mode === 'create' ? 'Add Account' : 'Edit Account'}
          </ModalHeader>
          <ModalCloseButton color="white" />
          
          <ModalBody>
            <VStack spacing={4} pb={6}>
              {/* Account Number */}
              <FormControl isInvalid={!!errors.account} isRequired>
                <FormLabel color="gray.300">Account Number</FormLabel>
                <Input
                  value={formData.account}
                  onChange={(e) => handleChange('account', e.target.value)}
                  placeholder="e.g., 1000, NL12RABO..."
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                  isDisabled={mode === 'edit'} // Cannot change account number
                />
                {errors.account && (
                  <FormErrorMessage>{errors.account}</FormErrorMessage>
                )}
                {mode === 'edit' && (
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    Account number cannot be changed
                  </Text>
                )}
              </FormControl>

              {/* Account Name */}
              <FormControl isInvalid={!!errors.accountName} isRequired>
                <FormLabel color="gray.300">Account Name</FormLabel>
                <Input
                  value={formData.accountName}
                  onChange={(e) => handleChange('accountName', e.target.value)}
                  placeholder="e.g., Kas, Bank, Crediteuren"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
                {errors.accountName && (
                  <FormErrorMessage>{errors.accountName}</FormErrorMessage>
                )}
              </FormControl>

              {/* Lookup Code */}
              <FormControl>
                <FormLabel color="gray.300">Lookup Code</FormLabel>
                <Input
                  value={formData.accountLookup}
                  onChange={(e) => handleChange('accountLookup', e.target.value)}
                  placeholder="e.g., CASH, BANK, PAYABLE"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              {/* Sub Parent */}
              <FormControl>
                <FormLabel color="gray.300">Sub Parent</FormLabel>
                <Input
                  value={formData.subParent}
                  onChange={(e) => handleChange('subParent', e.target.value)}
                  placeholder="Sub-parent account reference"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              {/* Parent */}
              <FormControl>
                <FormLabel color="gray.300">Parent</FormLabel>
                <Input
                  value={formData.parent}
                  onChange={(e) => handleChange('parent', e.target.value)}
                  placeholder="Parent account reference"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              {/* VW */}
              <FormControl>
                <FormLabel color="gray.300">VW</FormLabel>
                <Input
                  value={formData.vw}
                  onChange={(e) => handleChange('vw', e.target.value)}
                  placeholder="VW flag"
                  maxLength={1}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              {/* Tax Category */}
              <FormControl>
                <FormLabel color="gray.300">Tax Category</FormLabel>
                <Input
                  value={formData.belastingaangifte}
                  onChange={(e) => handleChange('belastingaangifte', e.target.value)}
                  placeholder="e.g., Activa, Passiva"
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              {/* Pattern */}
              <FormControl display="flex" alignItems="center">
                <FormLabel color="gray.300" mb={0}>Pattern</FormLabel>
                <Input
                  type="checkbox"
                  checked={formData.pattern}
                  onChange={(e) => handleChange('pattern', e.target.checked ? 'true' : 'false')}
                  width="auto"
                  ml={2}
                />
              </FormControl>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <HStack justify="space-between" width="100%" pt={4}>
              {/* Delete button (only in edit mode) */}
              {mode === 'edit' && onDelete && (
                <Button
                  colorScheme="red"
                  variant="outline"
                  onClick={onDeleteOpen}
                >
                  Delete
                </Button>
              )}
              
              <Box flex={1} />
              
              {/* Save/Cancel buttons */}
              <HStack spacing={3}>
                <Button variant="ghost" onClick={onClose} color="white">
                  Cancel
                </Button>
                <Button
                  colorScheme="orange"
                  onClick={handleSave}
                  isLoading={saving}
                  loadingText="Saving..."
                >
                  {mode === 'create' ? 'Create' : 'Save'}
                </Button>
              </HStack>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              Delete Account
            </AlertDialogHeader>

            <AlertDialogBody color="white">
              Are you sure you want to delete account <strong>{account?.Account}</strong>?
              <br />
              <br />
              <Text color="gray.400" fontSize="sm">
                Note: You cannot delete an account that is used in transactions.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose} color="white">
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

export default AccountModal;
