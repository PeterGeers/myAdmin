/**
 * EmailPreviewPanel — Displays a preview of the invoice email before sending.
 * Shows subject, HTML body, recipient, BCC, and attachment filename.
 * Provides "Confirm Send" button with loading state and close/cancel button.
 * Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §EmailPreviewPanel
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, Box, Text, VStack,
  HStack, Divider, Spinner,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

export interface EmailPreviewPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmSend: () => void;
  emailPreview: {
    subject: string;
    html_body: string;
    recipient: string;
    bcc: string;
    attachment_filename: string;
  } | null;
  isSending: boolean;
}

export const EmailPreviewPanel: React.FC<EmailPreviewPanelProps> = ({
  isOpen,
  onClose,
  onConfirmSend,
  emailPreview,
  isSending,
}) => {
  const { t } = useTypedTranslation('zzp');

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="xl"
      closeOnOverlayClick={!isSending}
      scrollBehavior="inside"
    >
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" maxW="700px">
        <ModalHeader>{t('invoices.email.panelTitle')}</ModalHeader>
        <ModalCloseButton isDisabled={isSending} />

        <ModalBody>
          {!emailPreview ? (
            <Box textAlign="center" py={8}>
              <Spinner size="lg" color="orange.400" />
            </Box>
          ) : (
            <VStack spacing={4} align="stretch">
              {/* Recipient */}
              <Box>
                <Text fontSize="sm" color="gray.400" fontWeight="semibold">
                  {t('invoices.email.recipientLabel')}
                </Text>
                <Text fontSize="sm" color="white">
                  {emailPreview.recipient}
                </Text>
              </Box>

              {/* BCC */}
              <Box>
                <Text fontSize="sm" color="gray.400" fontWeight="semibold">
                  {t('invoices.email.bccLabel')}
                </Text>
                <Text fontSize="sm" color="white">
                  {emailPreview.bcc}
                </Text>
              </Box>

              {/* Subject */}
              <Box>
                <Text fontSize="sm" color="gray.400" fontWeight="semibold">
                  {t('invoices.email.subjectLabel')}
                </Text>
                <Text fontSize="sm" color="white" fontWeight="medium">
                  {emailPreview.subject}
                </Text>
              </Box>

              {/* Attachment */}
              <Box>
                <Text fontSize="sm" color="gray.400" fontWeight="semibold">
                  {t('invoices.email.attachmentLabel')}
                </Text>
                <Text fontSize="sm" color="white">
                  📎 {emailPreview.attachment_filename}
                </Text>
              </Box>

              <Divider borderColor="gray.600" />

              {/* HTML Body */}
              <Box
                bg="white"
                color="black"
                borderRadius="md"
                p={4}
                maxH="300px"
                overflowY="auto"
                fontSize="sm"
                dangerouslySetInnerHTML={{ __html: emailPreview.html_body }}
              />
            </VStack>
          )}
        </ModalBody>

        <ModalFooter>
          <HStack spacing={3}>
            <Button
              variant="ghost"
              onClick={onClose}
              isDisabled={isSending}
            >
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              colorScheme="orange"
              onClick={onConfirmSend}
              isLoading={isSending}
              loadingText={t('invoices.email.sendButton')}
              isDisabled={!emailPreview || isSending}
            >
              {t('invoices.email.sendButton')}
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};
