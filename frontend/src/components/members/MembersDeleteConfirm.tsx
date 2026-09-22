/**
 * Members Delete confirmation (task 19.3) — a CONFIRM step before a destructive
 * delete, never a one-click delete. Uses the repo's confirm convention: a Chakra
 * `AlertDialog` with a `leastDestructiveRef` (Cancel), a red confirm button, and
 * `bg="gray.800"` dark styling — matching `frontend/src/pages/ZZPVehicles.tsx`,
 * `frontend/src/components/SysAdmin/RoleManagement.tsx` and
 * `frontend/src/components/TenantAdmin/ParameterManagement.tsx`.
 *
 * The dialog NAMES the member being deleted so the user knows exactly what they
 * are removing. On confirm it calls `deleteMember(memberId)` →
 * `DELETE /members/{member_id}` (scope/ownership enforced at the module edge —
 * the UI never invents scope). On success: toast, close, and refresh the list
 * via `onDeleted`. On error: toast the server message.
 *
 * _Requirements: R8.2_
 */

import React, { useRef, useState } from 'react';
import {
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter, Button, Text, useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { deleteMember } from '../../services/membersApiService';
import type { Member } from '../../types/members';

interface MembersDeleteConfirmProps {
  isOpen: boolean;
  onClose: () => void;
  /** The member to delete (its name is shown in the confirm body). */
  member: Member | null;
  /** Called after a successful delete so the page can refresh its list. */
  onDeleted: () => void;
}

export const MembersDeleteConfirm: React.FC<MembersDeleteConfirmProps> = ({
  isOpen, onClose, member, onDeleted,
}) => {
  const { t } = useTypedTranslation('members');
  const toast = useToast();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [deleting, setDeleting] = useState(false);

  // A friendly label for the member (name, else email, else id).
  const memberName =
    (member?.name as string) || (member?.email as string) || member?.member_id || '';

  const handleConfirm = async () => {
    if (!member) return;
    try {
      setDeleting(true);
      await deleteMember(member.member_id);
      toast({ title: t('deleteConfirm.toast.success'), status: 'success' });
      onDeleted();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('deleteConfirm.toast.error');
      toast({ title: message, status: 'error' });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AlertDialog
      isOpen={isOpen}
      leastDestructiveRef={cancelRef}
      onClose={onClose}
      isCentered
    >
      <AlertDialogOverlay>
        <AlertDialogContent bg="gray.800" color="white">
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            {t('deleteConfirm.title')}
          </AlertDialogHeader>
          <AlertDialogBody>
            {t('deleteConfirm.body')}{' '}
            <Text as="span" fontWeight="bold" color="orange.300">{memberName}</Text>?
            <br /><br />
            <Text color="red.400">{t('deleteConfirm.warning')}</Text>
          </AlertDialogBody>
          <AlertDialogFooter>
            <Button ref={cancelRef} variant="ghost" onClick={onClose}>
              {t('deleteConfirm.cancel')}
            </Button>
            <Button colorScheme="red" ml={3} onClick={handleConfirm} isLoading={deleting}>
              {t('deleteConfirm.confirm')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );
};

export default MembersDeleteConfirm;
