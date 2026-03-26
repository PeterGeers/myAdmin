/**
 * Account Modal Component
 * 
 * Modal for creating and editing chart of accounts entries.
 * Handles validation and provides delete functionality for existing accounts.
 */

import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
  Text,
  IconButton,
  Select,
  Switch,
  Divider
} from '@chakra-ui/react';
import { AccountModalProps, AccountFormData } from '../../types/chartOfAccounts';
import { buildApiUrl } from '../../services/apiService';

// Parameter definition from the API
interface ParamDefinition {
  key: string;
  type: 'boolean' | 'string' | 'string[]';
  label_en: string;
  label_nl: string;
  description_en: string;
  description_nl: string;
  module: string;
  depends_on?: string;
  options?: string[];
}

interface ParamEntry {
  key: string;
  value: string | boolean;
}

const AccountModal: React.FC<AccountModalProps> = ({
  isOpen,
  onClose,
  account,
  mode,
  onSave,
  onDelete
}) => {
  const { i18n } = useTranslation();
  const lang = i18n.language?.startsWith('nl') ? 'nl' : 'en';

  // Get localized label for a parameter definition
  const getParamLabel = (def: ParamDefinition) => lang === 'nl' ? def.label_nl : def.label_en;

  // Form state
  const [formData, setFormData] = useState<AccountFormData>({
    account: '',
    accountName: '',
    accountLookup: '',
    subParent: '',
    parent: '',
    vw: '',
    belastingaangifte: '',
    pattern: false,
    bank_account: false,
    iban: ''
  });
  
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editingParams, setEditingParams] = useState(false);
  const [paramEntries, setParamEntries] = useState<ParamEntry[]>([]);
  const [paramDefs, setParamDefs] = useState<ParamDefinition[]>([]);
  
  // Delete confirmation dialog
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Load parameter definitions from API
  useEffect(() => {
    const loadParamDefs = async () => {
      try {
        const url = buildApiUrl('/api/config/ledger-parameters');
        const response = await fetch(url);
        if (response.ok) {
          const defs = await response.json();
          setParamDefs(defs);
        }
      } catch (e) {
        console.warn('Failed to load ledger parameter definitions:', e);
      }
    };
    loadParamDefs();
  }, []);

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
          pattern: !!account.Pattern,
          bank_account: !!account.bank_account || !!account.Pattern,
          iban: account.iban || account.AccountLookup || ''
        });
        // Parse parameters into entries
        try {
          const params = account.parameters ? JSON.parse(account.parameters as string) : {};
          setParamEntries(Object.entries(params).map(([key, value]) => ({ key, value: value as string | boolean })));
        } catch {
          setParamEntries([]);
        }
      } else {
        setFormData({
          account: '',
          accountName: '',
          accountLookup: '',
          subParent: '',
          parent: '',
          vw: '',
          belastingaangifte: '',
          pattern: false,
          bank_account: false,
          iban: ''
        });
        setParamEntries([]);
      }
      setErrors({});
      setEditingParams(false);
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
      // Build parameters from entries if editing
      const saveData = { ...formData };
      if (editingParams || paramEntries.length > 0) {
        const paramsObj: Record<string, string | boolean> = {};
        paramEntries.forEach(entry => {
          if (entry.key.trim()) {
            paramsObj[entry.key.trim()] = entry.value;
          }
        });
        (saveData as any).parameters = Object.keys(paramsObj).length > 0 ? JSON.stringify(paramsObj) : null;
      }
      await onSave(saveData);
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

              {/* Parameters */}
              <Divider borderColor="gray.600" />
              <FormControl>
                <HStack justify="space-between" mb={2}>
                  <FormLabel color="gray.300" mb={0}>Parameters</FormLabel>
                  <Button
                    size="xs"
                    variant="outline"
                    colorScheme="orange"
                    onClick={() => setEditingParams(!editingParams)}
                  >
                    {editingParams ? 'Done' : 'Edit'}
                  </Button>
                </HStack>

                {!editingParams ? (
                  // Read-only view
                  <Box
                    bg="gray.700"
                    p={3}
                    borderRadius="md"
                    border="1px"
                    borderColor="gray.600"
                    fontSize="xs"
                    color="gray.300"
                    fontFamily="mono"
                    whiteSpace="pre-wrap"
                    wordBreak="break-all"
                    minH="40px"
                  >
                    {paramEntries.length > 0
                      ? paramEntries
                          .filter(e => e.key.trim())
                          .map(e => {
                            const def = paramDefs.find(d => d.key === e.key);
                            const label = def ? getParamLabel(def) : e.key;
                            const displayValue = typeof e.value === 'boolean' ? (e.value ? '✓' : '✗') : e.value;
                            return `${label}: ${displayValue}`;
                          })
                          .join('\n')
                      : lang === 'nl' ? 'Geen parameters' : 'No parameters'}
                  </Box>
                ) : (
                  // Editable key-value pairs
                  <VStack spacing={2} align="stretch">
                    {paramEntries.map((entry, idx) => {
                      // depends_on: hide entry if parent parameter is not set to true
                      const entryDef = paramDefs.find(d => d.key === entry.key);
                      if (entryDef?.depends_on) {
                        const parentEntry = paramEntries.find(e => e.key === entryDef.depends_on);
                        if (!parentEntry || parentEntry.value !== true) return null;
                      }

                      // Build filtered dropdown options: hide keys whose depends_on parent is not active
                      const availableKeys = paramDefs.filter(d => {
                        if (!d.depends_on) return true;
                        const parent = paramEntries.find(e => e.key === d.depends_on);
                        return parent && parent.value === true;
                      });

                      return (
                      <HStack key={idx} spacing={2}>
                        <Select
                          size="sm"
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          value={entry.key}
                          onChange={(e) => {
                            const newEntries = [...paramEntries];
                            const newKey = e.target.value;
                            const def = paramDefs.find(d => d.key === newKey);
                            newEntries[idx] = {
                              key: newKey,
                              value: def?.type === 'boolean' ? true : ''
                            };
                            setParamEntries(newEntries);
                          }}
                          flex={1}
                        >
                          <option value="">Select key...</option>
                          {availableKeys.map(d => (
                            <option key={d.key} value={d.key}>{getParamLabel(d)}</option>
                          ))}
                          {entry.key && !paramDefs.find(d => d.key === entry.key) && (
                            <option value={entry.key}>{entry.key}</option>
                          )}
                        </Select>

                        {paramDefs.find(d => d.key === entry.key)?.type === 'boolean' ? (
                          <Switch
                            isChecked={entry.value === true}
                            onChange={(e) => {
                              const newEntries = [...paramEntries];
                              newEntries[idx] = { ...entry, value: e.target.checked };
                              setParamEntries(newEntries);
                            }}
                            colorScheme="orange"
                          />
                        ) : (
                          <Input
                            size="sm"
                            bg="gray.700"
                            color="white"
                            borderColor="gray.600"
                            value={entry.value as string}
                            onChange={(e) => {
                              const newEntries = [...paramEntries];
                              newEntries[idx] = { ...entry, value: e.target.value };
                              setParamEntries(newEntries);
                            }}
                            placeholder="Value"
                            flex={1}
                          />
                        )}

                        <IconButton
                          aria-label="Remove parameter"
                          icon={<Text>✕</Text>}
                          size="sm"
                          variant="ghost"
                          colorScheme="red"
                          onClick={() => {
                            setParamEntries(paramEntries.filter((_, i) => i !== idx));
                          }}
                        />
                      </HStack>
                    );
                    })}

                    <Button
                      size="sm"
                      variant="outline"
                      colorScheme="orange"
                      onClick={() => setParamEntries([...paramEntries, { key: '', value: '' }])}
                    >
                      + Add parameter
                    </Button>
                  </VStack>
                )}
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
