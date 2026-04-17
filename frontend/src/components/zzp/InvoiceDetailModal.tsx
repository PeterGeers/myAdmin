/**
 * Modal wrapper for ZZPInvoiceDetail — opens from ZZPInvoices on row-click or new invoice.
 * Follows BankingProcessor pattern: row-click opens modal, primary actions in modal header.
 * Reference: .kiro/specs/zzp-module/design.md §6.3
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalCloseButton,
} from '@chakra-ui/react';
import ZZPInvoiceDetail from '../../pages/ZZPInvoiceDetail';

interface InvoiceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  invoiceId?: number | null;
  onSaved?: () => void;
}

export const InvoiceDetailModal: React.FC<InvoiceDetailModalProps> = ({
  isOpen, onClose, invoiceId, onSaved,
}) => (
  <Modal isOpen={isOpen} onClose={onClose} size="4xl" closeOnOverlayClick={false}
    scrollBehavior="inside">
    <ModalOverlay />
    <ModalContent bg="gray.800" color="white" maxW="900px">
      <ModalCloseButton />
      <ZZPInvoiceDetail
        invoiceId={invoiceId}
        onClose={onClose}
        onSaved={onSaved}
      />
    </ModalContent>
  </Modal>
);
