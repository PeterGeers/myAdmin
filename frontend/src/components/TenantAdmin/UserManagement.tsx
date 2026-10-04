/**
 * UserManagement Component
 *
 * Orchestrates user CRUD operations for the TenantAdmin page.
 * Delegates rendering to UserTable and UserInviteModal sub-components.
 */

import React, { useState, useEffect } from 'react';
import { Box, VStack, Button, Spinner, useToast, useDisclosure } from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
} from '../../services/apiService';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { UserTable, User } from './UserTable';
import { UserInviteModal, ModalMode } from './UserInviteModal';
import { Role } from './UserRoleEditor';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EmailTemplate {
  template_type: string;
  display_name: string;
}

interface UserManagementProps {
  tenant: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UserManagement({ tenant }: UserManagementProps) {
  const { t, i18n } = useTypedTranslation('admin');
  const lang = i18n.language;
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode>('details');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [editUserName, setEditUserName] = useState('');
  const [newUserPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState<string>('user_invitation');
  const [sendingEmail, setSendingEmail] = useState(false);

  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const emailTemplates: EmailTemplate[] = [
    { template_type: 'user_invitation', display_name: t('userManagement.emailTemplates.userInvitation') },
    { template_type: 'password_reset', display_name: t('userManagement.emailTemplates.passwordReset') },
    { template_type: 'account_update', display_name: t('userManagement.emailTemplates.accountUpdate') },
  ];

  // --- Filterable table ---
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

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  const loadData = async () => {
    setLoading(true);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        authenticatedGet('/api/tenant-admin/users', { tenant }),
        authenticatedGet('/api/tenant-admin/roles', { tenant }),
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
    if (tenant) loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  // ---------------------------------------------------------------------------
  // Modal openers
  // ---------------------------------------------------------------------------

  const openCreateModal = () => {
    setModalMode('create');
    setNewUserEmail('');
    setNewUserName('');
    setSelectedRoles([]);
    onOpen();
  };

  const openRolesModal = (user: User) => {
    setModalMode('edit-roles');
    setSelectedUser(user);
    setEditUserName(user.name || '');
    setSelectedRoles(user.groups);
    onOpen();
  };

  const openScopeModal = (user: User) => {
    setModalMode('edit-scope');
    setSelectedUser(user);
    onOpen();
  };

  const openDetailsModal = (user: User) => {
    setModalMode('details');
    setSelectedUser(user);
    setSelectedEmailTemplate('user_invitation');
    onOpen();
  };

  // ---------------------------------------------------------------------------
  // CRUD handlers
  // ---------------------------------------------------------------------------

  const handleCreateUser = async () => {
    setActionLoading(true);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      try {
        const response = await authenticatedPost(
          '/api/tenant-admin/users',
          {
            email: newUserEmail,
            name: newUserName,
            password: newUserPassword,
            groups: selectedRoles,
          },
          { tenant, signal: controller.signal },
        );

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
        } else if (response.status === 409) {
          toast({ title: t('userManagement.messages.userAlreadyExists'), description: data.message || data.error, status: 'warning', duration: 5000 });
        } else {
          throw new Error(data.error || 'Failed to create user');
        }
      } catch (fetchError: unknown) {
        clearTimeout(timeoutId);
        if (fetchError instanceof DOMException && fetchError.name === 'AbortError') {
          toast({ title: t('userManagement.messages.requestTimeout'), description: t('userManagement.messages.timeoutDescription'), status: 'warning', duration: 8000 });
          onClose();
          loadData();
          return;
        }
        throw fetchError;
      }
    } catch (error) {
      toast({ title: t('userManagement.messages.errorCreating'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!selectedUser) return;
    setActionLoading(true);
    try {
      if (editUserName !== (selectedUser.name || '')) {
        await authenticatedPut(
          `/api/tenant-admin/users/${selectedUser.username}`,
          { name: editUserName },
          { tenant },
        );
      }

      const currentRoles = selectedUser.groups;
      const rolesToAdd = selectedRoles.filter(r => !currentRoles.includes(r));
      const rolesToRemove = currentRoles.filter(r => !selectedRoles.includes(r));

      for (const role of rolesToAdd) {
        await authenticatedPost(
          `/api/tenant-admin/users/${selectedUser.username}/groups`,
          { groupName: role },
          { tenant },
        );
      }

      for (const role of rolesToRemove) {
        await authenticatedDelete(
          `/api/tenant-admin/users/${selectedUser.username}/groups/${role}`,
          { tenant },
        );
      }

      toast({ title: t('userManagement.messages.userUpdated'), status: 'success', duration: 3000 });
      onClose();
      loadData();
    } catch (error) {
      toast({ title: t('userManagement.messages.errorUpdating'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleUserStatus = async (user: User, enable: boolean) => {
    try {
      const response = await authenticatedPut(
        `/api/tenant-admin/users/${user.username}`,
        { enabled: enable },
        { tenant },
      );

      if (response.ok) {
        toast({ title: enable ? t('userManagement.messages.userEnabled') : t('userManagement.messages.userDisabled'), status: 'success', duration: 3000 });
        loadData();
      } else {
        throw new Error('Failed to update user status');
      }
    } catch (error) {
      toast({ title: t('userManagement.messages.errorUpdatingStatus'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (!window.confirm(t('userManagement.messages.confirmDelete', { email: user.email }))) return;
    try {
      const response = await authenticatedDelete(
        `/api/tenant-admin/users/${user.username}`,
        { tenant },
      );
      const data = await response.json();
      if (response.ok) {
        toast({ title: t('userManagement.messages.userDeleted'), description: data.message, status: 'success', duration: 3000 });
        loadData();
      } else {
        throw new Error(data.error || 'Failed to delete user');
      }
    } catch (error) {
      toast({ title: t('userManagement.messages.errorDeleting'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    }
  };

  const handleSendEmail = async () => {
    if (!selectedUser) return;
    setSendingEmail(true);
    try {
      const response = await authenticatedPost(
        '/api/tenant-admin/send-email',
        {
          email: selectedUser.email,
          template_type: selectedEmailTemplate,
          user_data: { name: selectedUser.name, username: selectedUser.username, status: selectedUser.status },
        },
        { tenant },
      );
      const data = await response.json();
      if (response.ok) {
        toast({ title: t('userManagement.messages.emailSent'), description: t('userManagement.messages.emailSentTo', { email: selectedUser.email }), status: 'success', duration: 3000 });
      } else {
        throw new Error(data.error || 'Failed to send email');
      }
    } catch (error) {
      toast({ title: t('userManagement.messages.errorSendingEmail'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setSendingEmail(false);
    }
  };

  const handleResendInvitation = async () => {
    if (!selectedUser) return;
    setSendingEmail(true);
    try {
      const response = await authenticatedPost(
        '/api/tenant-admin/resend-invitation',
        { email: selectedUser.email, username: selectedUser.username },
        { tenant },
      );
      const data = await response.json();
      if (response.ok) {
        toast({ title: t('userManagement.messages.invitationResent'), description: t('userManagement.messages.invitationResentMessage', { email: selectedUser.email, days: data.expiry_days }), status: 'success', duration: 5000 });
        loadData();
      } else if (data.email_failed && data.temporary_password) {
        const userEmail = selectedUser.email;
        const tempPw = data.temporary_password;
        const subject = encodeURIComponent('Your new myAdmin password');
        const body = encodeURIComponent(`Hi,\n\nYour password has been reset.\n\nTemporary password: ${tempPw}\n\nPlease log in and change your password.`);
        try { await navigator.clipboard.writeText(tempPw); } catch { /* ignore */ }
        toast({ title: 'Email could not be sent automatically', description: 'Password was reset and copied to clipboard. Your email client will open.', status: 'warning', duration: null, isClosable: true });
        window.open(`mailto:${userEmail}?subject=${subject}&body=${body}`, '_blank');
      } else {
        throw new Error(data.error || 'Failed to resend invitation');
      }
    } catch (error) {
      toast({ title: t('userManagement.messages.errorResendingInvitation'), description: error instanceof Error ? error.message : t('userManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setSendingEmail(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      <Button
        colorScheme="orange"
        leftIcon={<AddIcon />}
        onClick={openCreateModal}
        alignSelf="flex-end"
        size="sm"
      >
        {t('userManagement.createUser')}
      </Button>

      <UserTable
        users={filteredAndSortedUsers}
        filters={filters}
        setFilter={setFilter}
        sortField={sortField}
        sortDirection={sortDirection}
        handleSort={handleSort}
        onRowClick={openDetailsModal}
        t={t}
      />

      <UserInviteModal
        isOpen={isOpen}
        onClose={onClose}
        modalMode={modalMode}
        selectedUser={selectedUser}
        newUserEmail={newUserEmail}
        setNewUserEmail={setNewUserEmail}
        newUserName={newUserName}
        setNewUserName={setNewUserName}
        editUserName={editUserName}
        setEditUserName={setEditUserName}
        roles={roles}
        selectedRoles={selectedRoles}
        setSelectedRoles={setSelectedRoles}
        emailTemplates={emailTemplates}
        selectedEmailTemplate={selectedEmailTemplate}
        setSelectedEmailTemplate={setSelectedEmailTemplate}
        sendingEmail={sendingEmail}
        actionLoading={actionLoading}
        onCreateUser={handleCreateUser}
        onUpdateUser={handleUpdateUser}
        onSendEmail={handleSendEmail}
        onResendInvitation={handleResendInvitation}
        onToggleStatus={handleToggleUserStatus}
        onDelete={handleDeleteUser}
        onOpenRoles={openRolesModal}
        onOpenScope={openScopeModal}
        t={t}
        lang={lang}
      />
    </VStack>
  );
}
