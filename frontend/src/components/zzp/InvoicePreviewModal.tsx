/**
 * Modal for displaying a PDF preview of a draft ZZP invoice.
 * Uses browser-native PDF rendering via <iframe> with a blob URL.
 * Supports close (button + Escape), download, and error fallback.
 *
 * Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §Frontend Components
 */

import React, { useState, useCallback, useRef } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  ModalFooter,
  Button,
  Text,
  HStack,
  Box,
} from '@chakra-ui/react';
import { DownloadIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

export interface InvoicePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  pdfBlobUrl: string | null;
  invoiceNumber: string;
}

/**
 * InvoicePreviewModal — displays a PDF preview in a full-screen modal.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.2
 */
export const InvoicePreviewModal: React.FC<InvoicePreviewModalProps> = ({
  isOpen,
  onClose,
  pdfBlobUrl,
  invoiceNumber,
}) => {
  const { t } = useTypedTranslation('zzp');
  const [iframeError, setIframeError] = useState(false);
  const downloadRef = useRef<HTMLAnchorElement>(null);

  const downloadFilename = `${invoiceNumber}_PREVIEW.pdf`;

  const handleIframeError = useCallback(() => {
    setIframeError(true);
  }, []);

  const handleDownload = useCallback(() => {
    if (downloadRef.current && pdfBlobUrl) {
      downloadRef.current.click();
    }
  }, [pdfBlobUrl]);

  // Reset error state when modal opens with a new blob URL
  const handleModalOpen = useCallback(() => {
    setIframeError(false);
  }, []);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="full"
      closeOnEsc={true}
      closeOnOverlayClick={true}
      onCloseComplete={handleModalOpen}
    >
      <ModalOverlay bg="blackAlpha.700" />
      <ModalContent
        bg="gray.800"
        color="white"
        w="80vw"
        h="85vh"
        maxW="80vw"
        maxH="85vh"
        my="auto"
        mx="auto"
      >
        <ModalHeader>{t('invoices.preview.modalTitle')}</ModalHeader>
        <ModalCloseButton aria-label={t('invoices.preview.close')} />

        <ModalBody flex="1" overflow="hidden" p={0}>
          {pdfBlobUrl && !iframeError ? (
            <iframe
              src={pdfBlobUrl}
              title={t('invoices.preview.modalTitle')}
              width="100%"
              height="100%"
              style={{ border: 'none' }}
              onError={handleIframeError}
            />
          ) : (
            <Box
              display="flex"
              flexDirection="column"
              alignItems="center"
              justifyContent="center"
              h="100%"
              p={8}
            >
              <Text color="red.300" fontSize="lg" mb={4}>
                {t('invoices.preview.renderError')}
              </Text>
              {pdfBlobUrl && (
                <Button
                  colorScheme="orange"
                  leftIcon={<DownloadIcon />}
                  onClick={handleDownload}
                >
                  {t('invoices.preview.download')}
                </Button>
              )}
            </Box>
          )}
        </ModalBody>

        <ModalFooter borderTop="1px solid" borderColor="gray.600">
          <HStack spacing={3}>
            <Button variant="ghost" onClick={onClose}>
              {t('invoices.preview.close')}
            </Button>
            {pdfBlobUrl && (
              <Button
                colorScheme="orange"
                leftIcon={<DownloadIcon />}
                onClick={handleDownload}
              >
                {t('invoices.preview.download')}
              </Button>
            )}
          </HStack>
        </ModalFooter>

        {/* Hidden download anchor */}
        {pdfBlobUrl && (
          <a
            ref={downloadRef}
            href={pdfBlobUrl}
            download={downloadFilename}
            style={{ display: 'none' }}
            aria-hidden="true"
          >
            download
          </a>
        )}
      </ModalContent>
    </Modal>
  );
};

export default InvoicePreviewModal;
