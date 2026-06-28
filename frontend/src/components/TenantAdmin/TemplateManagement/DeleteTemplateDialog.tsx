/**
 * Delete Template Dialog Component
 *
 * Confirmation dialog for deleting a tenant-specific template.
 * On deletion, the system reverts to the built-in default template.
 */

import React from 'react';
import {
  Button,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
} from '@chakra-ui/react';

interface DeleteTemplateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  deleting: boolean;
  templateLabel: string;
  cancelRef: React.RefObject<HTMLButtonElement>;
}

export const DeleteTemplateDialog: React.FC<DeleteTemplateDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  deleting,
  templateLabel,
  cancelRef,
}) => {
  return (
    <AlertDialog
      isOpen={isOpen}
      leastDestructiveRef={cancelRef}
      onClose={onClose}
    >
      <AlertDialogOverlay>
        <AlertDialogContent>
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            Delete Template
          </AlertDialogHeader>

          <AlertDialogBody>
            Are you sure you want to delete the tenant template for{' '}
            <strong>{templateLabel}</strong>?
            The system will revert to using the built-in default template.
          </AlertDialogBody>

          <AlertDialogFooter>
            <Button ref={cancelRef} onClick={onClose} isDisabled={deleting}>
              Cancel
            </Button>
            <Button
              colorScheme="red"
              onClick={onConfirm}
              isLoading={deleting}
              loadingText="Deleting..."
              ml={3}
            >
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );
};

export default DeleteTemplateDialog;
