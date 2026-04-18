import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Table, Thead, Tbody, Tr, Td,
  Badge, useToast, Spinner, Text, Modal, ModalOverlay, ModalContent,
  ModalHeader, ModalBody, ModalFooter, ModalCloseButton, useDisclosure,
  Checkbox, Stack, FormControl, FormLabel, Input, Select
} from '@chakra-ui/react';
import { EditIcon, AddIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '../../config';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';

interface User {
  username: string;
  email: string;
  name?: string;
  status: string;
  enabled: boolean;
  groups: string[];
  tenants: string[];
  created: string;
}

interface Role {
  name: string;
  description: string;
  precedence: number | null;
}

interface EmailTemplate {
  template_type: string;
  display_name: string;
}

interface UserManagementProps {
  tenant: string;
}

export default function UserManagement({ tenant }: UserManagementProps) {
  const { t } = useTypedTranslation('admin');
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [modalMode, setModalMode] = useState<'edit' | 'create' | 'details'>('edit');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [editUserName, setEditUserName] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState<string>('user_invitation');
  const [sendingEmail, setSendingEmail] = useState(false);
  
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  // Available email templates
  const emailTemplates: EmailTemplate[] = [
    { template_type: 'user_invitation', display_name: t('userManagement.emailTemplates.userInvitation') },
    { template_type: 'password_reset', display_name: t('userManagement.emailTemplates.passwordReset') },
    { template_type: 'account_update', display_name: t('userManagement.emailTemplates.accountUpdate') },
  ];

  const loadData = async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      if (!token) {
        throw new Error(t('userManagement.messages.noAuthToken'));
      }

      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant': tenant
      };

      const [usersRes, rolesRes] = await Promise.all([
        fetch(buildApiUrl('/api/tenant-admin/users'), { headers }),
        fetch(buildApiUrl('/api/tenant-admin/roles'), { headers })
      ]);

      if (usersRes.ok && rolesRes.ok) {
        const usersData = await usersRes.json();
        const rolesData = await rolesRes.json();
        setUsers(usersData.users || []);
        setRoles(rolesData.roles || []);
      } else {
        const usersError = await usersRes.text();
        const rolesError = await rolesRes.text();
        throw new Error(`Failed to load data: ${usersError || rolesError}`);
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorLoading'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tenant) {
      loadData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  // Column text filters + sort via framework hook
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData: filteredAndSortedUsers,
  } = useFilterableTable<User>(users, {
    initialFilters: { email: '', name: '', status: '', groups: '', created: '', tenants: '' },
    defaultSort: { field: 'email', direction: 'asc' },
  });

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  const openCreateModal = () => {
    setModalMode('create');
    setNewUserEmail('');
    setNewUserName('');
    setNewUserPassword('');
    setSelectedRoles([]);
    onOpen();
  };

  const openEditModal = (user: User) => {
    setModalMode('edit');
    setSelectedUser(user);
    setEditUserName(user.name || '');
    setSelectedRoles(user.groups);
    onOpen();
  };

  const openDetailsModal = (user: User) => {
    setModalMode('details');
    setSelectedUser(user);
    setSelectedEmailTemplate('user_invitation');
    onOpen();
  };

  const handleCreateUser = async () => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      // Create abort controller for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
      
      try {
        const response = await fetch(buildApiUrl('/api/tenant-admin/users'), {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Tenant': tenant
          },
          body: JSON.stringify({
            email: newUserEmail,
            name: newUserName,
            password: newUserPassword,
            groups: selectedRoles
          }),
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        const data = await response.json();

        if (response.ok) {
          const successMessage = data.existing_user 
            ? `${data.message}. ${t('userManagement.messages.userExistsMessage')}`
            : data.message;
          
          toast({
            title: data.existing_user ? t('userManagement.messages.userAddedToTenant') : t('userManagement.messages.userCreated'),
            description: successMessage,
            status: 'success',
          duration: 5000,
        });
        onClose();
        loadData();
      } else {
        // Handle specific error cases
        if (response.status === 409) {
          // User already in this tenant
          toast({
            title: t('userManagement.messages.userAlreadyExists'),
            description: data.message || data.error,
            status: 'warning',
            duration: 5000,
          });
        } else {
          throw new Error(data.error || 'Failed to create user');
        }
      }
      } catch (fetchError: any) {
        clearTimeout(timeoutId);
        
        // Handle timeout specifically
        if (fetchError.name === 'AbortError') {
          toast({
            title: t('userManagement.messages.requestTimeout'),
            description: t('userManagement.messages.timeoutDescription'),
            status: 'warning',
            duration: 8000,
          });
          // Still close modal and reload - user may have been created
          onClose();
          loadData();
          return;
        }
        throw fetchError;
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorCreating'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      // Update display name if changed
      if (editUserName !== (selectedUser.name || '')) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}`), {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Tenant': tenant
          },
          body: JSON.stringify({ name: editUserName })
        });
      }

      // Update roles
      const currentRoles = selectedUser.groups;
      const rolesToAdd = selectedRoles.filter(r => !currentRoles.includes(r));
      const rolesToRemove = currentRoles.filter(r => !selectedRoles.includes(r));

      // Add roles
      for (const role of rolesToAdd) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}/groups`), {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Tenant': tenant
          },
          body: JSON.stringify({ groupName: role })
        });
      }

      // Remove roles
      for (const role of rolesToRemove) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}/groups/${role}`), {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`,
            'X-Tenant': tenant
          }
        });
      }

      toast({
        title: t('userManagement.messages.userUpdated'),
        status: 'success',
        duration: 3000,
      });
      onClose();
      loadData();
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorUpdating'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleUserStatus = async (user: User, enable: boolean) => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/tenant-admin/users/${user.username}`), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({ enabled: enable })
      });

      if (response.ok) {
        toast({
          title: enable ? t('userManagement.messages.userEnabled') : t('userManagement.messages.userDisabled'),
          status: 'success',
          duration: 3000,
        });
        loadData();
      } else {
        throw new Error('Failed to update user status');
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorUpdatingStatus'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (!window.confirm(t('userManagement.messages.confirmDelete', { email: user.email }))) {
      return;
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/tenant-admin/users/${user.username}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant
        }
      });

      const data = await response.json();

      if (response.ok) {
        toast({
          title: t('userManagement.messages.userDeleted'),
          description: data.message,
          status: 'success',
          duration: 3000,
        });
        loadData();
      } else {
        throw new Error(data.error || 'Failed to delete user');
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorDeleting'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleSendEmail = async () => {
    if (!selectedUser) return;

    setSendingEmail(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl('/api/tenant-admin/send-email'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({
          email: selectedUser.email,
          template_type: selectedEmailTemplate,
          user_data: {
            name: selectedUser.name,
            username: selectedUser.username,
            status: selectedUser.status
          }
        })
      });

      const data = await response.json();

      if (response.ok) {
        toast({
          title: t('userManagement.messages.emailSent'),
          description: t('userManagement.messages.emailSentTo', { email: selectedUser.email }),
          status: 'success',
          duration: 3000,
        });
      } else {
        throw new Error(data.error || 'Failed to send email');
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorSendingEmail'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSendingEmail(false);
    }
  };

  const handleResendInvitation = async () => {
    if (!selectedUser) return;

    setSendingEmail(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl('/api/tenant-admin/resend-invitation'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({
          email: selectedUser.email,
          username: selectedUser.username
        })
      });

      const data = await response.json();

      if (response.ok) {
        toast({
          title: t('userManagement.messages.invitationResent'),
          description: t('userManagement.messages.invitationResentMessage', { 
            email: selectedUser.email, 
            days: data.expiry_days 
          }),
          status: 'success',
          duration: 5000,
        });
        loadData(); // Refresh user list
      } else if (data.email_failed && data.temporary_password) {
        const userEmail = selectedUser.email;
        const tempPw = data.temporary_password;
        const subject = encodeURIComponent('Your new myAdmin password');
        const body = encodeURIComponent(
          `Hi,\n\nYour password has been reset.\n\nTemporary password: ${tempPw}\n\nPlease log in and change your password.`
        );
        try { await navigator.clipboard.writeText(tempPw); } catch { /* ignore */ }
        toast({
          title: 'Email could not be sent automatically',
          description: 'Password was reset and copied to clipboard. Your email client will open.',
          status: 'warning',
          duration: null,
          isClosable: true,
        });
        window.open(`mailto:${userEmail}?subject=${subject}&body=${body}`, '_blank');
      } else {
        throw new Error(data.error || 'Failed to resend invitation');
      }
    } catch (error) {
      toast({
        title: t('userManagement.messages.errorResendingInvitation'),
        description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSendingEmail(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* Primary action */}
      <Button
        colorScheme="orange"
        leftIcon={<AddIcon />}
        onClick={openCreateModal}
        alignSelf="flex-end"
        size="sm"
      >
        {t('userManagement.createUser')}
      </Button>

      {/* Users Table */}
      <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <FilterableHeader
                label={t('userManagement.table.email')}
                filterValue={filters.email}
                onFilterChange={(v) => setFilter('email', v)}
                sortable
                sortDirection={columnSortDirection('email')}
                onSort={() => handleSort('email')}
              />
              <FilterableHeader
                label={t('userManagement.table.name')}
                filterValue={filters.name}
                onFilterChange={(v) => setFilter('name', v)}
                sortable
                sortDirection={columnSortDirection('name')}
                onSort={() => handleSort('name')}
              />
              <FilterableHeader
                label={t('userManagement.table.status')}
                filterValue={filters.status}
                onFilterChange={(v) => setFilter('status', v)}
                sortable
                sortDirection={columnSortDirection('status')}
                onSort={() => handleSort('status')}
              />
              <FilterableHeader
                label={t('userManagement.table.roles')}
                filterValue={filters.groups}
                onFilterChange={(v) => setFilter('groups', v)}
              />
              <FilterableHeader
                label={t('userManagement.table.created')}
                filterValue={filters.created}
                onFilterChange={(v) => setFilter('created', v)}
                sortable
                sortDirection={columnSortDirection('created')}
                onSort={() => handleSort('created')}
              />
              <FilterableHeader
                label={t('userManagement.table.tenants')}
                filterValue={filters.tenants}
                onFilterChange={(v) => setFilter('tenants', v)}
              />
            </Tr>
          </Thead>
          <Tbody>
            {filteredAndSortedUsers.map(user => (
              <Tr
                key={user.username}
                _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                onClick={() => openDetailsModal(user)}
              >
                <Td color="orange.400" fontWeight="bold">
                  {user.email}
                </Td>
                <Td color="white">{user.name || '-'}</Td>
                <Td>
                  <Badge colorScheme={user.enabled ? 'green' : 'red'}>
                    {user.status}
                  </Badge>
                </Td>
                <Td>
                  <HStack spacing={1} wrap="wrap">
                    {user.groups.map(group => (
                      <Badge key={group} colorScheme="blue" fontSize="xs">
                        {group}
                      </Badge>
                    ))}
                  </HStack>
                </Td>
                <Td color="gray.400" fontSize="sm">
                  {new Date(user.created).toLocaleDateString()}
                </Td>
                <Td>
                  <HStack spacing={1} wrap="wrap">
                    {user.tenants.map(t => (
                      <Badge key={t} colorScheme="purple" fontSize="xs">
                        {t}
                      </Badge>
                    ))}
                  </HStack>
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>

        {filteredAndSortedUsers.length === 0 && (
          <Text color="gray.400" textAlign="center" py={8}>
            {t('userManagement.table.noUsers')}
          </Text>
        )}
      </Box>

      {/* Create/Edit/Details User Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="orange.400">
            {modalMode === 'create' && t('userManagement.modal.createTitle')}
            {modalMode === 'edit' && t('userManagement.modal.editTitle')}
            {modalMode === 'details' && t('userManagement.modal.detailsTitle')}
          </ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            {modalMode === 'details' && selectedUser ? (
              <VStack spacing={4} align="stretch">
                {/* User Information */}
                <Box bg="gray.700" p={4} borderRadius="md">
                  <VStack spacing={3} align="stretch">
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">{t('userManagement.modal.email')}:</Text>
                      <Text color="white" fontWeight="bold">{selectedUser.email}</Text>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">{t('userManagement.modal.displayName')}:</Text>
                      <Text color="white">{selectedUser.name || '-'}</Text>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">{t('userManagement.table.status')}:</Text>
                      <Badge colorScheme={selectedUser.enabled ? 'green' : 'red'}>
                        {selectedUser.status}
                      </Badge>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">{t('userManagement.table.created')}:</Text>
                      <Text color="white" fontSize="sm">
                        {new Date(selectedUser.created).toLocaleString()}
                      </Text>
                    </HStack>
                  </VStack>
                </Box>

                {/* Roles */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>{t('userManagement.modal.roles')}:</Text>
                  <HStack spacing={2} wrap="wrap">
                    {selectedUser.groups.map(group => (
                      <Badge key={group} colorScheme="blue">
                        {group}
                      </Badge>
                    ))}
                  </HStack>
                </Box>

                {/* Tenants */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>{t('userManagement.table.tenants')}:</Text>
                  <HStack spacing={2} wrap="wrap">
                    {selectedUser.tenants.map(t => (
                      <Badge key={t} colorScheme="purple">
                        {t}
                      </Badge>
                    ))}
                  </HStack>
                </Box>

                {/* Send Email Section */}
                <Box bg="gray.700" p={4} borderRadius="md" borderWidth="1px" borderColor="orange.500">
                  <Text color="orange.400" fontWeight="bold" mb={3}>{t('userManagement.modal.sendEmail')}</Text>
                  <VStack spacing={3}>
                    {selectedUser.status === 'FORCE_CHANGE_PASSWORD' && (
                      <Button
                        colorScheme="orange"
                        width="full"
                        onClick={handleResendInvitation}
                        isLoading={sendingEmail}
                      >
                        {t('userManagement.modal.resendInvitation')}
                      </Button>
                    )}
                    <FormControl>
                      <FormLabel color="gray.300" fontSize="sm">{t('userManagement.modal.emailTemplate')}</FormLabel>
                      <Select
                        value={selectedEmailTemplate}
                        onChange={(e) => setSelectedEmailTemplate(e.target.value)}
                        bg="gray.600"
                        color="white"
                        borderColor="gray.500"
                      >
                        {emailTemplates.map(template => (
                          <option key={template.template_type} value={template.template_type}>
                            {template.display_name}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                    <Button
                      colorScheme="orange"
                      variant="outline"
                      width="full"
                      onClick={handleSendEmail}
                      isLoading={sendingEmail}
                    >
                      {t('userManagement.modal.sendEmailButton')}
                    </Button>
                  </VStack>
                </Box>

                {/* Action Buttons */}
                <Box borderTop="1px" borderColor="gray.700" pt={4} mt={4}>
                  <HStack spacing={2} justify="flex-start">
                    <Button
                      colorScheme="blue"
                      variant="ghost"
                      leftIcon={<EditIcon />}
                      onClick={() => {
                        onClose();
                        setTimeout(() => openEditModal(selectedUser), 100);
                      }}
                      color="blue.400"
                    >
                      {t('userManagement.editUser')}
                    </Button>
                    <Button
                      colorScheme={selectedUser.enabled ? 'yellow' : 'green'}
                      variant="ghost"
                      onClick={() => {
                        handleToggleUserStatus(selectedUser, !selectedUser.enabled);
                        onClose();
                      }}
                      color={selectedUser.enabled ? 'yellow.400' : 'green.400'}
                    >
                      {selectedUser.enabled ? t('userManagement.modal.disable') : t('userManagement.modal.enable')}
                    </Button>
                    <Button
                      colorScheme="red"
                      variant="ghost"
                      onClick={() => {
                        onClose();
                        setTimeout(() => handleDeleteUser(selectedUser), 100);
                      }}
                      color="red.400"
                    >
                      {t('userManagement.modal.delete')}
                    </Button>
                  </HStack>
                </Box>
              </VStack>
            ) : (
              <VStack spacing={4}>
              {modalMode === 'create' && (
                <>
                  <FormControl isRequired>
                    <FormLabel color="gray.300">{t('userManagement.modal.email')}</FormLabel>
                    <Input
                      type="email"
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                      placeholder={t('userManagement.modal.emailPlaceholder')}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel color="gray.300">{t('userManagement.modal.displayName')}</FormLabel>
                    <Input
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                      placeholder={t('userManagement.modal.displayNamePlaceholder')}
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel color="gray.300">{t('userManagement.modal.temporaryPassword')}</FormLabel>
                    <Input
                      type="text"
                      value={t('userManagement.modal.temporaryPasswordAutoGenerated')}
                      isReadOnly
                      bg="gray.800"
                      color="gray.400"
                      borderColor="gray.700"
                      cursor="not-allowed"
                    />
                  </FormControl>
                </>
              )}

              {modalMode === 'edit' && (
                <FormControl>
                  <FormLabel color="gray.300">{t('userManagement.modal.displayName')}</FormLabel>
                  <Input
                    value={editUserName}
                    onChange={(e) => setEditUserName(e.target.value)}
                    bg="gray.700"
                    color="white"
                    borderColor="gray.600"
                  />
                </FormControl>
              )}

              <FormControl>
                <FormLabel color="gray.300">{t('userManagement.modal.roles')}</FormLabel>
                <Stack spacing={2} bg="gray.700" p={3} borderRadius="md">
                  {roles.map(role => (
                    <Checkbox
                      key={role.name}
                      isChecked={selectedRoles.includes(role.name)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedRoles([...selectedRoles, role.name]);
                        } else {
                          setSelectedRoles(selectedRoles.filter(r => r !== role.name));
                        }
                      }}
                      colorScheme="orange"
                      color="white"
                    >
                      <VStack align="start" spacing={0}>
                        <Text fontWeight="bold">{role.name}</Text>
                        {role.description && (
                          <Text fontSize="xs" color="gray.400">{role.description}</Text>
                        )}
                      </VStack>
                    </Checkbox>
                  ))}
                </Stack>
              </FormControl>
            </VStack>
            )}
          </ModalBody>

          {modalMode !== 'details' && (
            <ModalFooter>
              <Button variant="ghost" mr={3} onClick={onClose} color="white">
                {t('userManagement.modal.cancel')}
              </Button>
              <Button
                colorScheme="orange"
                onClick={modalMode === 'create' ? handleCreateUser : handleUpdateUser}
                isLoading={actionLoading}
              >
                {modalMode === 'create' ? t('userManagement.modal.create') : t('userManagement.modal.update')}
              </Button>
            </ModalFooter>
          )}
          {modalMode === 'details' && (
            <ModalFooter>
              <Button variant="ghost" onClick={onClose} color="white">
                {t('userManagement.modal.close')}
              </Button>
            </ModalFooter>
          )}
        </ModalContent>
      </Modal>
    </VStack>
  );
}
