import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Input, Textarea, NumberInput, NumberInputField,
  NumberInputStepper, NumberIncrementStepper, NumberDecrementStepper,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { getRoles, createRole, updateRole, deleteRole, Role } from '../../services/sysadminService';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

export function RoleManagement() {
  const { t } = useTypedTranslation('admin');
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    precedence: 100
  });
  
  const toast = useToast();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  useEffect(() => {
    loadRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRoles = async () => {
    setLoading(true);
    try {
      const data = await getRoles();
      
      const categorizedRoles = data.roles.map(role => {
        let category: 'platform' | 'module' | 'other' = 'other';
        
        if (role.name === 'SysAdmin' || role.name === 'Tenant_Admin') {
          category = 'platform';
        } else if (role.name.includes('_')) {
          category = 'module';
        }
        
        return { ...role, category };
      });
      
      setRoles(categorizedRoles);
    } catch (error) {
      toast({
        title: t('roleManagement.messages.errorLoading'),
        description: error instanceof Error ? error.message : t('roleManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const openCreateModal = () => {
    setFormData({ name: '', description: '', precedence: 100 });
    setModalMode('create');
    setSelectedRole(null);
    onModalOpen();
  };

  const openEditModal = (role: Role) => {
    setFormData({
      name: role.name,
      description: role.description || '',
      precedence: role.precedence || 100
    });
    setModalMode('edit');
    setSelectedRole(role);
    onModalOpen();
  };

  const handleSubmit = async () => {
    if (modalMode === 'create') {
      await handleCreateRole();
    } else {
      await handleUpdateRole();
    }
  };

  const handleCreateRole = async () => {
    if (!formData.name.trim()) {
      toast({
        title: t('roleManagement.messages.validationError'),
        description: t('roleManagement.messages.roleNameRequired'),
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setActionLoading(true);
    try {
      await createRole({
        name: formData.name.trim(),
        description: formData.description.trim(),
        precedence: formData.precedence
      });

      toast({
        title: t('roleManagement.messages.roleCreated'),
        description: t('roleManagement.messages.roleCreatedSuccess', { name: formData.name }),
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      loadRoles();
    } catch (error) {
      toast({
        title: t('roleManagement.messages.errorCreating'),
        description: error instanceof Error ? error.message : t('roleManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateRole = async () => {
    if (!selectedRole) return;

    setActionLoading(true);
    try {
      await updateRole(selectedRole.name, {
        description: formData.description.trim(),
        precedence: formData.precedence
      });

      toast({
        title: t('roleManagement.messages.roleUpdated'),
        description: t('roleManagement.messages.roleUpdatedSuccess', { name: selectedRole.name }),
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      setSelectedRole(null);
      loadRoles();
    } catch (error) {
      toast({
        title: t('roleManagement.messages.errorUpdating'),
        description: error instanceof Error ? error.message : t('roleManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteRole = async () => {
    if (!selectedRole) return;

    setActionLoading(true);
    try {
      await deleteRole(selectedRole.name);

      toast({
        title: t('roleManagement.messages.roleDeleted'),
        description: t('roleManagement.messages.roleDeletedSuccess', { name: selectedRole.name }),
        status: 'success',
        duration: 3000,
      });

      onDeleteClose();
      setSelectedRole(null);
      loadRoles();
    } catch (error) {
      toast({
        title: t('roleManagement.messages.errorDeleting'),
        description: error instanceof Error ? error.message : t('roleManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const openDeleteDialog = (role: Role) => {
    setSelectedRole(role);
    onDeleteOpen();
  };

  const getCategoryColor = (category?: string) => {
    switch (category) {
      case 'platform': return 'purple';
      case 'module': return 'blue';
      default: return 'gray';
    }
  };

  const getCategoryLabel = (category?: string) => {
    switch (category) {
      case 'platform': return t('roleManagement.categories.platform');
      case 'module': return t('roleManagement.categories.module');
      default: return t('roleManagement.categories.other');
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">{t('roleManagement.loading')}</Text>
        </VStack>
      </Box>
    );
  }

  const platformRoles = roles.filter(r => r.category === 'platform');
  const moduleRoles = roles.filter(r => r.category === 'module');
  const otherRoles = roles.filter(r => r.category === 'other');

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        <HStack justify="space-between">
          <Text color="gray.300" fontSize="lg">
            {t('roleManagement.totalRoles')}: <Text as="span" color="orange.400" fontWeight="bold">{roles.length}</Text>
          </Text>
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={openCreateModal}>
            {t('roleManagement.createRole')}
          </Button>
        </HStack>

        {platformRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              {t('roleManagement.categories.platformRoles')} ({platformRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {platformRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <HStack>
                      <Text 
                        color="orange.400" 
                        fontWeight="bold"
                        cursor="pointer"
                        _hover={{ textDecoration: 'underline', color: 'orange.300' }}
                        onClick={() => openEditModal(role)}
                      >
                        {role.name}
                      </Text>
                      <Badge colorScheme={getCategoryColor(role.category)} fontSize="xs">
                        {getCategoryLabel(role.category)}
                      </Badge>
                      {role.user_count !== undefined && (
                        <Badge colorScheme="green" fontSize="xs">
                          {role.user_count} {role.user_count === 1 ? t('roleManagement.labels.user') : t('roleManagement.labels.users')}
                        </Badge>
                      )}
                    </HStack>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">{t('roleManagement.labels.precedence')}: {role.precedence}</Badge>
                    <Button
                      size="sm"
                      colorScheme="red"
                      variant="ghost"
                      leftIcon={<DeleteIcon />}
                      onClick={() => openDeleteDialog(role)}
                      isDisabled={role.name === 'SysAdmin' || role.name === 'Tenant_Admin'}
                    >
                      {t('roleManagement.deleteRole')}
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}

        {moduleRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              {t('roleManagement.categories.moduleRoles')} ({moduleRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {moduleRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <HStack>
                      <Text 
                        color="orange.400" 
                        fontWeight="bold"
                        cursor="pointer"
                        _hover={{ textDecoration: 'underline', color: 'orange.300' }}
                        onClick={() => openEditModal(role)}
                      >
                        {role.name}
                      </Text>
                      <Badge colorScheme={getCategoryColor(role.category)} fontSize="xs">
                        {getCategoryLabel(role.category)}
                      </Badge>
                      {role.user_count !== undefined && (
                        <Badge colorScheme="green" fontSize="xs">
                          {role.user_count} {role.user_count === 1 ? t('roleManagement.labels.user') : t('roleManagement.labels.users')}
                        </Badge>
                      )}
                    </HStack>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">{t('roleManagement.labels.precedence')}: {role.precedence}</Badge>
                    <Button size="sm" colorScheme="red" variant="ghost" leftIcon={<DeleteIcon />} onClick={() => openDeleteDialog(role)}>
                      {t('roleManagement.deleteRole')}
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}

        {otherRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              {t('roleManagement.categories.otherRoles')} ({otherRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {otherRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <HStack>
                      <Text 
                        color="orange.400" 
                        fontWeight="bold"
                        cursor="pointer"
                        _hover={{ textDecoration: 'underline', color: 'orange.300' }}
                        onClick={() => openEditModal(role)}
                      >
                        {role.name}
                      </Text>
                      {role.user_count !== undefined && (
                        <Badge colorScheme="green" fontSize="xs">
                          {role.user_count} {role.user_count === 1 ? t('roleManagement.labels.user') : t('roleManagement.labels.users')}
                        </Badge>
                      )}
                    </HStack>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">{t('roleManagement.labels.precedence')}: {role.precedence}</Badge>
                    <Button size="sm" colorScheme="red" variant="ghost" leftIcon={<DeleteIcon />} onClick={() => openDeleteDialog(role)}>
                      {t('roleManagement.deleteRole')}
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}
      </VStack>

      <Modal isOpen={isModalOpen} onClose={onModalClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">
            {modalMode === 'create' ? t('roleManagement.modal.createTitle') : t('roleManagement.modal.editTitle', { name: selectedRole?.name })}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired isDisabled={modalMode === 'edit'}>
                <FormLabel color="white">{t('roleManagement.modal.roleName')}</FormLabel>
                <Input
                  placeholder={t('roleManagement.modal.roleNamePlaceholder')}
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'edit'}
                />
                {modalMode === 'create' && (
                  <Text fontSize="xs" color="gray.400" mt={1}>
                    {t('roleManagement.modal.roleNameHintCreate')}
                  </Text>
                )}
                {modalMode === 'edit' && (
                  <Text fontSize="xs" color="gray.400" mt={1}>
                    {t('roleManagement.modal.roleNameHintEdit')}
                  </Text>
                )}
              </FormControl>

              <FormControl>
                <FormLabel color="white">{t('roleManagement.modal.description')}</FormLabel>
                <Textarea
                  placeholder={t('roleManagement.modal.descriptionPlaceholder')}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  rows={3}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="white">{t('roleManagement.modal.precedence')}</FormLabel>
                <NumberInput
                  value={formData.precedence}
                  onChange={(_, value) => setFormData({ ...formData, precedence: value })}
                  min={1}
                  max={999}
                  bg="gray.600"
                >
                  <NumberInputField borderColor="gray.500" color="white" />
                  <NumberInputStepper>
                    <NumberIncrementStepper borderColor="gray.500" />
                    <NumberDecrementStepper borderColor="gray.500" />
                  </NumberInputStepper>
                </NumberInput>
                <Text fontSize="xs" color="gray.400" mt={1}>
                  {t('roleManagement.modal.precedenceHint')}
                </Text>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onModalClose}>{t('roleManagement.modal.cancel')}</Button>
            <Button colorScheme="orange" onClick={handleSubmit} isLoading={actionLoading}>
              {modalMode === 'create' ? t('roleManagement.modal.create') : t('roleManagement.modal.update')}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              {t('roleManagement.deleteDialog.title')}
            </AlertDialogHeader>
            <AlertDialogBody>
              {t('roleManagement.deleteDialog.confirmMessage')} <Text as="span" fontWeight="bold" color="orange.400">"{selectedRole?.name}"</Text>?
              <br /><br />
              <Text color="red.400">{t('roleManagement.deleteDialog.warning')}</Text>
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>{t('roleManagement.deleteDialog.cancel')}</Button>
              <Button colorScheme="red" onClick={handleDeleteRole} ml={3} isLoading={actionLoading}>
                {t('roleManagement.deleteDialog.delete')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}

export default RoleManagement;
