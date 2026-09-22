/**
 * UserInviteModal Component
 *
 * Focused, single-purpose modals for user management, all reached from the
 * user-details view:
 *   - `create`      → new-user form (email + name + roles)
 *   - `details`     → read-only summary + action row
 *   - `edit-roles`  → "Rollen bewerken": role checkboxes (+ display name)
 *   - `edit-scope`  → "Scope bewerken": the per-user MEMBER scope editor
 *
 * Every modal conforms to the app modal standard (steering 32 "Modal Layout"):
 *   - scrollBehavior="inside" + closeOnOverlayClick={false} so nothing ever
 *     falls off-screen; body scrolls, header/footer stay pinned.
 *   - responsive size + capped ModalContent height (maxH="85vh").
 *   - ModalFooter with EXACTLY ONE primary Save: Cancel (ghost, left) + Save
 *     (orange, right, isLoading).
 *   - dark theme (bg="gray.800" color="white"), orange headers, white close.
 *
 * The old merged "Edit user" (roles + scope in one form) is gone: roles and
 * scope now each live in their own single-purpose modal. The Scope modal drives
 * the UserScopeEditor's save through an imperative handle so the footer owns the
 * single Save (no competing in-editor Save button).
 */

import React, { useRef, useState } from 'react';
import {
  VStack, HStack, Button, Badge, Text, Box, Divider,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, FormControl, FormLabel, Input, Select,
} from '@chakra-ui/react';
import { EditIcon } from '@chakra-ui/icons';
import { UserRoleEditor, Role } from './UserRoleEditor';
import {
  UserScopeEditor, UserScopeEditorHandle, holdsMembersCapabilityRole,
} from './UserScopeEditor';
import type { User } from './UserTable';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EmailTemplate {
  template_type: string;
  display_name: string;
}

export type ModalMode = 'create' | 'details' | 'edit-roles' | 'edit-scope';

interface UserInviteModalProps {
  isOpen: boolean;
  onClose: () => void;
  modalMode: ModalMode;
  selectedUser: User | null;
  // Create fields
  newUserEmail: string;
  setNewUserEmail: (v: string) => void;
  newUserName: string;
  setNewUserName: (v: string) => void;
  // Edit fields
  editUserName: string;
  setEditUserName: (v: string) => void;
  // Role selection
  roles: Role[];
  selectedRoles: string[];
  setSelectedRoles: (roles: string[]) => void;
  // Email
  emailTemplates: EmailTemplate[];
  selectedEmailTemplate: string;
  setSelectedEmailTemplate: (v: string) => void;
  sendingEmail: boolean;
  // Actions
  actionLoading: boolean;
  onCreateUser: () => void;
  onUpdateUser: () => void;
  onSendEmail: () => void;
  onResendInvitation: () => void;
  onToggleStatus: (user: User, enable: boolean) => void;
  onDelete: (user: User) => void;
  onOpenRoles: (user: User) => void;
  onOpenScope: (user: User) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
  /** Current UI language, for localized scope-dimension labels. */
  lang: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const UserInviteModal: React.FC<UserInviteModalProps> = ({
  isOpen,
  onClose,
  modalMode,
  selectedUser,
  newUserEmail,
  setNewUserEmail,
  newUserName,
  setNewUserName,
  editUserName,
  setEditUserName,
  roles,
  selectedRoles,
  setSelectedRoles,
  emailTemplates,
  selectedEmailTemplate,
  setSelectedEmailTemplate,
  sendingEmail,
  actionLoading,
  onCreateUser,
  onUpdateUser,
  onSendEmail,
  onResendInvitation,
  onToggleStatus,
  onDelete,
  onOpenRoles,
  onOpenScope,
  t,
  lang,
}) => {
  const scopeRef = useRef<UserScopeEditorHandle>(null);
  const [scopeSaving, setScopeSaving] = useState(false);

  const handleScopeSave = async () => {
    const ok = await scopeRef.current?.save();
    if (ok) onClose();
  };

  // The Scope modal is a touch wider to fit the value pickers comfortably.
  const size = modalMode === 'edit-roles'
    ? { base: 'sm' as const, md: 'lg' as const }
    : { base: 'sm' as const, md: 'xl' as const };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size={size}
      scrollBehavior="inside"
      closeOnOverlayClick={false}
    >
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" maxH="85vh">
        <ModalHeader color="orange.400">
          {modalMode === 'create' && t('userManagement.modal.createTitle')}
          {modalMode === 'details' && t('userManagement.modal.detailsTitle')}
          {modalMode === 'edit-roles' && t('userManagement.modal.editRolesTitle')}
          {modalMode === 'edit-scope' && t('userManagement.modal.editScopeTitle')}
        </ModalHeader>
        <ModalCloseButton color="white" />
        <ModalBody>
          {modalMode === 'details' && selectedUser && (
            <DetailsView
              user={selectedUser}
              emailTemplates={emailTemplates}
              selectedEmailTemplate={selectedEmailTemplate}
              setSelectedEmailTemplate={setSelectedEmailTemplate}
              sendingEmail={sendingEmail}
              onSendEmail={onSendEmail}
              onResendInvitation={onResendInvitation}
              onToggleStatus={onToggleStatus}
              onDelete={onDelete}
              onOpenRoles={onOpenRoles}
              onOpenScope={onOpenScope}
              onClose={onClose}
              t={t}
            />
          )}

          {modalMode === 'create' && (
            <CreateForm
              newUserEmail={newUserEmail}
              setNewUserEmail={setNewUserEmail}
              newUserName={newUserName}
              setNewUserName={setNewUserName}
              roles={roles}
              selectedRoles={selectedRoles}
              setSelectedRoles={setSelectedRoles}
              t={t}
            />
          )}

          {modalMode === 'edit-roles' && (
            <RolesForm
              editUserName={editUserName}
              setEditUserName={setEditUserName}
              roles={roles}
              selectedRoles={selectedRoles}
              setSelectedRoles={setSelectedRoles}
              t={t}
            />
          )}

          {modalMode === 'edit-scope' && selectedUser && (
            <UserScopeEditor
              ref={scopeRef}
              username={selectedUser.username}
              t={t}
              lang={lang}
              hideInternalSave
              onSavingChange={setScopeSaving}
            />
          )}
        </ModalBody>

        {modalMode === 'details' && (
          <ModalFooter>
            <Button variant="ghost" onClick={onClose} color="white">
              {t('userManagement.modal.close')}
            </Button>
          </ModalFooter>
        )}

        {modalMode === 'create' && (
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose} color="white">
              {t('userManagement.modal.cancel')}
            </Button>
            <Button colorScheme="orange" onClick={onCreateUser} isLoading={actionLoading}>
              {t('userManagement.modal.create')}
            </Button>
          </ModalFooter>
        )}

        {modalMode === 'edit-roles' && (
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose} color="white">
              {t('userManagement.modal.cancel')}
            </Button>
            <Button colorScheme="orange" onClick={onUpdateUser} isLoading={actionLoading}>
              {t('userManagement.modal.update')}
            </Button>
          </ModalFooter>
        )}

        {modalMode === 'edit-scope' && (
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose} color="white">
              {t('userManagement.modal.cancel')}
            </Button>
            <Button colorScheme="orange" onClick={handleScopeSave} isLoading={scopeSaving}>
              {t('userManagement.scope.save')}
            </Button>
          </ModalFooter>
        )}
      </ModalContent>
    </Modal>
  );
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface DetailsViewProps {
  user: User;
  emailTemplates: EmailTemplate[];
  selectedEmailTemplate: string;
  setSelectedEmailTemplate: (v: string) => void;
  sendingEmail: boolean;
  onSendEmail: () => void;
  onResendInvitation: () => void;
  onToggleStatus: (user: User, enable: boolean) => void;
  onDelete: (user: User) => void;
  onOpenRoles: (user: User) => void;
  onOpenScope: (user: User) => void;
  onClose: () => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

const DetailsView: React.FC<DetailsViewProps> = ({
  user,
  emailTemplates,
  selectedEmailTemplate,
  setSelectedEmailTemplate,
  sendingEmail,
  onSendEmail,
  onResendInvitation,
  onToggleStatus,
  onDelete,
  onOpenRoles,
  onOpenScope,
  onClose,
  t,
}) => (
  <VStack spacing={4} align="stretch">
    {/* User Information */}
    <Box bg="gray.700" p={4} borderRadius="md">
      <VStack spacing={3} align="stretch">
        <HStack justify="space-between">
          <Text color="gray.400" fontSize="sm">{t('userManagement.modal.email')}:</Text>
          <Text color="white" fontWeight="bold">{user.email}</Text>
        </HStack>
        <HStack justify="space-between">
          <Text color="gray.400" fontSize="sm">{t('userManagement.modal.displayName')}:</Text>
          <Text color="white">{user.name || '-'}</Text>
        </HStack>
        <HStack justify="space-between">
          <Text color="gray.400" fontSize="sm">{t('userManagement.table.status')}:</Text>
          <Badge colorScheme={user.enabled ? 'green' : 'red'}>
            {user.status}
          </Badge>
        </HStack>
        <HStack justify="space-between">
          <Text color="gray.400" fontSize="sm">{t('userManagement.table.created')}:</Text>
          <Text color="white" fontSize="sm">
            {new Date(user.created).toLocaleString()}
          </Text>
        </HStack>
      </VStack>
    </Box>

    {/* Roles */}
    <Box>
      <Text color="gray.300" fontWeight="bold" mb={2}>{t('userManagement.modal.roles')}:</Text>
      <HStack spacing={2} wrap="wrap">
        {user.groups.map(group => (
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
        {user.tenants.map(tenantName => (
          <Badge key={tenantName} colorScheme="purple">
            {tenantName}
          </Badge>
        ))}
      </HStack>
    </Box>

    {/* Send Email Section */}
    <Box bg="gray.700" p={4} borderRadius="md" borderWidth="1px" borderColor="orange.500">
      <Text color="orange.400" fontWeight="bold" mb={3}>{t('userManagement.modal.sendEmail')}</Text>
      <VStack spacing={3}>
        {user.status === 'FORCE_CHANGE_PASSWORD' && (
          <Button
            colorScheme="orange"
            width="full"
            onClick={onResendInvitation}
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
          onClick={onSendEmail}
          isLoading={sendingEmail}
        >
          {t('userManagement.modal.sendEmailButton')}
        </Button>
      </VStack>
    </Box>

    {/* Action Buttons — roles and scope are edited via dedicated single-purpose
        modals. "Scope bewerken" only shows for a user holding a Members
        capability role (R4.6). Disable/Enable + Delete stay reachable here. */}
    <Divider borderColor="gray.700" />
    <HStack spacing={2} justify="flex-start" wrap="wrap">
      <Button
        colorScheme="blue"
        variant="ghost"
        leftIcon={<EditIcon />}
        onClick={() => onOpenRoles(user)}
        color="blue.400"
      >
        {t('userManagement.modal.editRoles')}
      </Button>
      {holdsMembersCapabilityRole(user.groups) && (
        <Button
          colorScheme="teal"
          variant="ghost"
          leftIcon={<EditIcon />}
          onClick={() => onOpenScope(user)}
          color="teal.300"
        >
          {t('userManagement.modal.editScope')}
        </Button>
      )}
      <Button
        colorScheme={user.enabled ? 'yellow' : 'green'}
        variant="ghost"
        onClick={() => {
          onToggleStatus(user, !user.enabled);
          onClose();
        }}
        color={user.enabled ? 'yellow.400' : 'green.400'}
      >
        {user.enabled ? t('userManagement.modal.disable') : t('userManagement.modal.enable')}
      </Button>
      <Button
        colorScheme="red"
        variant="ghost"
        onClick={() => {
          onClose();
          setTimeout(() => onDelete(user), 100);
        }}
        color="red.400"
      >
        {t('userManagement.modal.delete')}
      </Button>
    </HStack>
  </VStack>
);

interface CreateFormProps {
  newUserEmail: string;
  setNewUserEmail: (v: string) => void;
  newUserName: string;
  setNewUserName: (v: string) => void;
  roles: Role[];
  selectedRoles: string[];
  setSelectedRoles: (roles: string[]) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

const CreateForm: React.FC<CreateFormProps> = ({
  newUserEmail,
  setNewUserEmail,
  newUserName,
  setNewUserName,
  roles,
  selectedRoles,
  setSelectedRoles,
  t,
}) => (
  <VStack spacing={4} align="stretch">
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

    <UserRoleEditor
      roles={roles}
      selectedRoles={selectedRoles}
      onRolesChange={setSelectedRoles}
      label={t('userManagement.modal.roles')}
    />
  </VStack>
);

interface RolesFormProps {
  editUserName: string;
  setEditUserName: (v: string) => void;
  roles: Role[];
  selectedRoles: string[];
  setSelectedRoles: (roles: string[]) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

const RolesForm: React.FC<RolesFormProps> = ({
  editUserName,
  setEditUserName,
  roles,
  selectedRoles,
  setSelectedRoles,
  t,
}) => (
  <VStack spacing={4} align="stretch">
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

    <UserRoleEditor
      roles={roles}
      selectedRoles={selectedRoles}
      onRolesChange={setSelectedRoles}
      label={t('userManagement.modal.roles')}
    />
  </VStack>
);
