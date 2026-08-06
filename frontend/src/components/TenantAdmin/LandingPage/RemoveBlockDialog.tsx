/**
 * RemoveBlockDialog — Confirmation dialog before deleting a block.
 */

import React, { useRef } from 'react';
import {
  AlertDialog, AlertDialogOverlay, AlertDialogContent,
  AlertDialogHeader, AlertDialogBody, AlertDialogFooter,
  Button,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

interface RemoveBlockDialogProps {
  isOpen: boolean;
  blockType: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function RemoveBlockDialog({ isOpen, blockType, onConfirm, onCancel }: RemoveBlockDialogProps) {
  const { t } = useTypedTranslation('admin');
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <AlertDialog
      isOpen={isOpen}
      leastDestructiveRef={cancelRef}
      onClose={onCancel}
    >
      <AlertDialogOverlay>
        <AlertDialogContent bg="gray.800" borderColor="gray.600">
          <AlertDialogHeader fontSize="lg" fontWeight="bold" color="white">
            {t('landingPage.editor.removeBlockTitle')}
          </AlertDialogHeader>

          <AlertDialogBody color="gray.300">
            {t('landingPage.editor.removeBlockConfirm', { type: blockType })}
          </AlertDialogBody>

          <AlertDialogFooter>
            <Button ref={cancelRef} onClick={onCancel} size="sm">
              {t('landingPage.editor.cancel')}
            </Button>
            <Button colorScheme="red" onClick={onConfirm} ml={3} size="sm">
              {t('landingPage.editor.remove')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );
}
