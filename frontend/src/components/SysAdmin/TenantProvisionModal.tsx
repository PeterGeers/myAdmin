/**
 * TenantProvisionModal Component
 *
 * Create/Edit/View modal for tenant management, including
 * form fields, module selection, provisioning actions, and delete confirmation.
 */

import React from 'react';
import {
  VStack, HStack, Button, Text, Badge, Box,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, FormControl, FormLabel,
  Checkbox, Stack, Input, Select,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay,
} from '@chakra-ui/react';
import type { Tenant } from '../../services/sysadminService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TenantFormData {
  administration: string;
  display_name: string;
  contact_email: string;
  phone_number: string;
  street_address: string;
  city: string;
  zipcode: string;
  country: string;
  status: 'active' | 'suspended' | 'inactive' | 'deleted';
  enabled_modules: string[];
  locale: 'nl' | 'en';
}

interface TenantProvisionModalProps {
  // Modal state
  isOpen: boolean;
  onClose: () => void;
  modalMode: 'create' | 'edit' | 'view';
  selectedTenant: Tenant | null;
  // Form
  formData: TenantFormData;
  setFormData: React.Dispatch<React.SetStateAction<TenantFormData>>;
  // Actions
  actionLoading: boolean;
  onCreate: () => void;
  onUpdate: () => void;
  onReprovision: () => void;
  onResendInvitation: () => void;
  onOpenDelete: () => void;
  onOpenEdit: (tenant: Tenant) => void;
  onOpenModules: () => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

interface DeleteDialogProps {
  isOpen: boolean;
  onClose: () => void;
  selectedTenant: Tenant | null;
  actionLoading: boolean;
  onDelete: () => void;
  cancelRef: React.RefObject<HTMLButtonElement | null>;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const getStatusColor = (status: string) => {
  switch (status) {
    case 'active': return 'green';
    case 'suspended': return 'orange';
    case 'inactive': return 'gray';
    case 'deleted': return 'red';
    default: return 'gray';
  }
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const TenantProvisionModal: React.FC<TenantProvisionModalProps> = ({
  isOpen,
  onClose,
  modalMode,
  selectedTenant,
  formData,
  setFormData,
  actionLoading,
  onCreate,
  onUpdate,
  onReprovision,
  onResendInvitation,
  onOpenDelete,
  onOpenEdit,
  onOpenModules,
  t,
}) => {
  const toggleModule = (module: string) => {
    setFormData(prev => ({
      ...prev,
      enabled_modules: prev.enabled_modules.includes(module)
        ? prev.enabled_modules.filter(m => m !== module)
        : [...prev.enabled_modules, module],
    }));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="orange.400">
          {modalMode === 'create' && t('tenantManagement.modal.createTitle')}
          {modalMode === 'edit' && t('tenantManagement.modal.editTitle', { name: selectedTenant?.display_name })}
          {modalMode === 'view' && t('tenantManagement.modal.viewTitle', { name: selectedTenant?.display_name })}
        </ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            {/* Administration ID */}
            <FormControl isRequired={modalMode === 'create'} isDisabled={modalMode === 'view' || modalMode === 'edit'}>
              <FormLabel color="white">{t('tenantManagement.modal.administrationId')}</FormLabel>
              <Input
                placeholder={t('tenantManagement.modal.administrationPlaceholder')}
                value={formData.administration}
                onChange={(e) => setFormData(prev => ({ ...prev, administration: e.target.value.toLowerCase() }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'edit' || modalMode === 'view'}
              />
              {modalMode === 'create' && (
                <Text fontSize="xs" color="gray.400" mt={1}>{t('tenantManagement.modal.administrationHelp')}</Text>
              )}
            </FormControl>

            {/* Display Name */}
            <FormControl isRequired isDisabled={modalMode === 'view'}>
              <FormLabel color="white">{t('tenantManagement.modal.displayName')}</FormLabel>
              <Input
                placeholder={t('tenantManagement.modal.displayNamePlaceholder')}
                value={formData.display_name}
                onChange={(e) => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'view'}
              />
            </FormControl>

            {/* Contact Email */}
            <FormControl isRequired isDisabled={modalMode === 'view'}>
              <FormLabel color="white">{t('tenantManagement.modal.contactEmail')}</FormLabel>
              <Input
                type="email"
                placeholder={t('tenantManagement.modal.contactEmailPlaceholder')}
                value={formData.contact_email}
                onChange={(e) => setFormData(prev => ({ ...prev, contact_email: e.target.value }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'view'}
              />
            </FormControl>

            {/* Status (edit only) */}
            {modalMode === 'edit' && (
              <FormControl>
                <FormLabel color="white">{t('tenantManagement.statusLabel')}</FormLabel>
                <Select
                  value={formData.status}
                  onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value as TenantFormData['status'] }))}
                  bg="gray.600" color="white" borderColor="gray.500"
                >
                  <option style={{ background: '#2D3748', color: 'white' }} value="active">{t('tenantManagement.status.active')}</option>
                  <option style={{ background: '#2D3748', color: 'white' }} value="suspended">{t('tenantManagement.status.suspended')}</option>
                  <option style={{ background: '#2D3748', color: 'white' }} value="inactive">{t('tenantManagement.status.inactive')}</option>
                </Select>
              </FormControl>
            )}

            {/* Phone */}
            <FormControl isDisabled={modalMode === 'view'}>
              <FormLabel color="white">{t('tenantManagement.modal.phoneNumber')}</FormLabel>
              <Input
                placeholder={t('tenantManagement.modal.phonePlaceholder')}
                value={formData.phone_number}
                onChange={(e) => setFormData(prev => ({ ...prev, phone_number: e.target.value }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'view'}
              />
            </FormControl>

            {/* Street */}
            <FormControl isDisabled={modalMode === 'view'}>
              <FormLabel color="white">{t('tenantManagement.modal.streetAddress')}</FormLabel>
              <Input
                placeholder={t('tenantManagement.modal.streetPlaceholder')}
                value={formData.street_address}
                onChange={(e) => setFormData(prev => ({ ...prev, street_address: e.target.value }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'view'}
              />
            </FormControl>

            {/* City + Zipcode */}
            <HStack>
              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.city')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.cityPlaceholder')}
                  value={formData.city}
                  onChange={(e) => setFormData(prev => ({ ...prev, city: e.target.value }))}
                  bg="gray.600" color="white" borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>
              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.zipcode')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.zipcodePlaceholder')}
                  value={formData.zipcode}
                  onChange={(e) => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                  bg="gray.600" color="white" borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>
            </HStack>

            {/* Country */}
            <FormControl isDisabled={modalMode === 'view'}>
              <FormLabel color="white">{t('tenantManagement.modal.country')}</FormLabel>
              <Input
                placeholder={t('tenantManagement.modal.countryPlaceholder')}
                value={formData.country}
                onChange={(e) => setFormData(prev => ({ ...prev, country: e.target.value }))}
                bg="gray.600" color="white" borderColor="gray.500"
                _placeholder={{ color: 'gray.400' }}
                isReadOnly={modalMode === 'view'}
              />
            </FormControl>

            {/* Locale (create only) */}
            {modalMode === 'create' && (
              <FormControl>
                <FormLabel color="gray.300">{t('tenantManagement.modal.locale')}</FormLabel>
                <Select
                  value={formData.locale}
                  onChange={(e) => setFormData(prev => ({ ...prev, locale: e.target.value as 'nl' | 'en' }))}
                  bg="gray.600" color="white" borderColor="gray.500"
                >
                  <option value="nl" style={{ background: '#2D3748' }}>{t('tenantManagement.modal.localeNL')}</option>
                  <option value="en" style={{ background: '#2D3748' }}>{t('tenantManagement.modal.localeEN')}</option>
                </Select>
                <Text fontSize="xs" color="gray.500" mt={1}>{t('tenantManagement.modal.localeHint')}</Text>
              </FormControl>
            )}

            {/* Modules (create only) */}
            {modalMode === 'create' && (
              <FormControl>
                <FormLabel color="gray.300">{t('tenantManagement.modal.enabledModules')}</FormLabel>
                <Stack spacing={2}>
                  <Checkbox isChecked={formData.enabled_modules.includes('FIN')} onChange={() => toggleModule('FIN')} colorScheme="orange">
                    <Text color="gray.300">{t('tenantManagement.modal.moduleFinancial')}</Text>
                  </Checkbox>
                  <Checkbox isChecked={formData.enabled_modules.includes('STR')} onChange={() => toggleModule('STR')} colorScheme="orange">
                    <Text color="gray.300">{t('tenantManagement.modal.moduleSTR')}</Text>
                  </Checkbox>
                  <Checkbox isChecked={formData.enabled_modules.includes('ZZP')} onChange={() => toggleModule('ZZP')} colorScheme="orange">
                    <Text color="gray.300">{t('tenantManagement.modal.moduleZZP')}</Text>
                  </Checkbox>
                </Stack>
                <Text fontSize="xs" color="gray.500" mt={1}>{t('tenantManagement.modal.moduleAutoAdded')}</Text>
              </FormControl>
            )}

            {/* View-only info */}
            {modalMode === 'view' && selectedTenant && (
              <Box>
                <Text color="gray.400" fontSize="sm" mb={2}>{t('tenantManagement.modal.additionalInfo')}</Text>
                <VStack align="stretch" spacing={2} fontSize="sm">
                  <HStack>
                    <Text color="gray.500">{t('tenantManagement.statusLabel')}:</Text>
                    <Badge colorScheme={getStatusColor(selectedTenant.status)}>
                      {t(`tenantManagement.status.${selectedTenant.status}`)}
                    </Badge>
                  </HStack>
                  <HStack>
                    <Text color="gray.500">{t('tenantManagement.modal.userCount')}:</Text>
                    <Text color="gray.300">{selectedTenant.user_count}</Text>
                  </HStack>
                  <HStack>
                    <Text color="gray.500">{t('tenantManagement.modal.createdAt')}:</Text>
                    <Text color="gray.300">{new Date(selectedTenant.created_at).toLocaleString()}</Text>
                  </HStack>
                  {selectedTenant.updated_at && (
                    <HStack>
                      <Text color="gray.500">{t('tenantManagement.modal.updatedAt')}:</Text>
                      <Text color="gray.300">{new Date(selectedTenant.updated_at).toLocaleString()}</Text>
                    </HStack>
                  )}
                </VStack>
              </Box>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          {modalMode === 'view' ? (
            <>
              <Button variant="ghost" mr={3} onClick={onClose}>{t('tenantManagement.actions.close')}</Button>
              <Button colorScheme="orange" onClick={() => { onClose(); onOpenEdit(selectedTenant!); }}>
                {t('tenantManagement.actions.edit')}
              </Button>
            </>
          ) : modalMode === 'edit' ? (
            <>
              <Button
                variant="ghost" mr="auto" colorScheme="red"
                onClick={() => { onClose(); onOpenDelete(); }}
                isDisabled={selectedTenant?.administration === 'myAdmin'}
              >
                {t('tenantManagement.actions.delete')}
              </Button>
              <Button
                variant="outline" colorScheme="green"
                onClick={onReprovision} isLoading={actionLoading}
                title={t('tenantManagement.actions.reprovisionTooltip')}
              >
                {t('tenantManagement.actions.reprovision')}
              </Button>
              <Button
                variant="outline" colorScheme="purple"
                onClick={onResendInvitation} isLoading={actionLoading}
                isDisabled={selectedTenant?.status === 'deleted'}
                title={selectedTenant?.status === 'deleted'
                  ? t('tenantManagement.actions.resendDisabledDeleted')
                  : t('tenantManagement.actions.resendInvitationTooltip')}
              >
                {t('tenantManagement.actions.resendInvitation')}
              </Button>
              <Button variant="outline" colorScheme="blue" onClick={() => { onClose(); onOpenModules(); }}>
                {t('tenantManagement.actions.manageModules')}
              </Button>
              <Button variant="ghost" mr={3} onClick={onClose}>{t('tenantManagement.actions.cancel')}</Button>
              <Button colorScheme="orange" onClick={onUpdate} isLoading={actionLoading}>
                {t('tenantManagement.actions.update')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" mr={3} onClick={onClose}>{t('tenantManagement.actions.cancel')}</Button>
              <Button colorScheme="orange" onClick={onCreate} isLoading={actionLoading}>
                {t('tenantManagement.actions.create')}
              </Button>
            </>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

// ---------------------------------------------------------------------------
// Delete Dialog
// ---------------------------------------------------------------------------

export const TenantDeleteDialog: React.FC<DeleteDialogProps> = ({
  isOpen,
  onClose,
  selectedTenant,
  actionLoading,
  onDelete,
  cancelRef,
  t,
}) => (
  <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
    <AlertDialogOverlay>
      <AlertDialogContent bg="gray.800" color="white">
        <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
          {t('tenantManagement.deleteDialog.title')}
        </AlertDialogHeader>
        <AlertDialogBody>
          {t('tenantManagement.deleteDialog.confirmMessage')} <Text as="span" fontWeight="bold" color="orange.400">"{selectedTenant?.display_name}"</Text>?
          <br /><br />
          <Text color="red.400">{t('tenantManagement.deleteDialog.warning')}</Text>
          {selectedTenant && selectedTenant.user_count > 0 && (
            <>
              <br />
              <Text color="orange.400">{t('tenantManagement.deleteDialog.hasUsers', { count: selectedTenant.user_count })}</Text>
            </>
          )}
        </AlertDialogBody>
        <AlertDialogFooter>
          <Button ref={cancelRef} onClick={onClose}>{t('tenantManagement.actions.cancel')}</Button>
          <Button colorScheme="red" onClick={onDelete} ml={3} isLoading={actionLoading}>
            {t('tenantManagement.actions.delete')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialogOverlay>
  </AlertDialog>
);
