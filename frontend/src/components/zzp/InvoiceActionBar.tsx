/**
 * InvoiceActionBar — header row with invoice number, status badge, and action buttons.
 * Extracted from ZZPInvoiceDetail to reduce file size.
 */

import React from 'react';
import { Flex, HStack, Text, Button } from '@chakra-ui/react';
import { ViewIcon } from '@chakra-ui/icons';
import { Invoice } from '../../types/zzp';
import { InvoiceStatusBadge } from './InvoiceStatusBadge';

export interface InvoiceActionBarProps {
  invoice: Invoice | null;
  isEditable: boolean;
  isDraft: boolean;
  // Loading states
  saving: boolean;
  sending: boolean;
  loadingEmailPreview: boolean;
  previewing: boolean;
  crediting: boolean;
  reminding: boolean;
  // Handlers
  onSave: () => void;
  onSendInvoice: () => void;
  onPreview: () => void;
  onCreditNote: () => void;
  onSendReminder: () => void;
  onClose: () => void;
  // i18n
  t: (key: string, fallback?: string) => string;
}

export const InvoiceActionBar: React.FC<InvoiceActionBarProps> = ({
  invoice, isEditable, isDraft,
  saving, sending, loadingEmailPreview, previewing, crediting, reminding,
  onSave, onSendInvoice, onPreview, onCreditNote, onSendReminder, onClose,
  t,
}) => {
  return (
    <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
      <HStack spacing={3}>
        <Text fontSize="lg" fontWeight="bold" color="white">
          {invoice ? invoice.invoice_number : t('invoices.newInvoice', 'New Invoice')}
        </Text>
        {invoice && <InvoiceStatusBadge status={invoice.status} />}
        {invoice?.invoice_type === 'credit_note' && (
          <Text fontSize="sm" color="purple.300">({t('invoices.creditNote', 'Credit Note')})</Text>
        )}
      </HStack>
      <HStack spacing={2}>
        {isEditable && (
          <Button colorScheme="orange" size="sm" onClick={onSave}
            isLoading={saving}>
            {t('common.save', 'Save')}
          </Button>
        )}
        {invoice && isDraft && (
          <Button colorScheme="blue" size="sm" onClick={onSendInvoice}
            isLoading={sending || loadingEmailPreview} isDisabled={saving}>
            {t('invoices.send', 'Send')}
          </Button>
        )}
        {invoice && invoice.status === 'draft' && (
          <Button
            leftIcon={<ViewIcon />}
            size="sm"
            variant="outline"
            colorScheme="teal"
            onClick={onPreview}
            isLoading={previewing}
            loadingText={t('invoices.preview.loading', 'Generating preview...')}
            isDisabled={previewing || saving}
          >
            {t('invoices.preview.button', 'Preview PDF')}
          </Button>
        )}
        {invoice && invoice.status === 'sent' && invoice.invoice_type !== 'credit_note' && (
          <Button colorScheme="purple" size="sm" variant="outline"
            onClick={onCreditNote} isLoading={crediting}>
            {t('invoices.createCreditNote', 'Credit Note')}
          </Button>
        )}
        {invoice && (invoice.status === 'sent' || invoice.status === 'overdue') && (
          <Button colorScheme="red" size="sm" variant="outline"
            onClick={onSendReminder} isLoading={reminding}>
            {t('debtors.sendReminder', 'Send Reminder')}
          </Button>
        )}
        <Button variant="ghost" size="sm" color="gray.400" onClick={onClose}>
          {t('common.cancel', 'Cancel')}
        </Button>
      </HStack>
    </Flex>
  );
};
