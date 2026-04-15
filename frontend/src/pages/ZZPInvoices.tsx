/**
 * ZZP Invoices page — Chakra Table with filters and header actions.
 * Follows BankingProcessor pattern: row-click opens detail, no inline buttons.
 * Reference: .kiro/specs/zzp-module/design.md §4.3, §6.2
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Input, Select,
  Table, Thead, Tbody, Tr, Th, Td, HStack, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, CopyIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Invoice, InvoiceStatus, InvoiceFilters, Contact } from '../types/zzp';
import { getInvoices, copyLastInvoice } from '../services/zzpInvoiceService';
import { getContacts } from '../services/contactService';
import { InvoiceStatusBadge } from '../components/zzp/InvoiceStatusBadge';
import { InvoiceDetailModal } from '../components/zzp/InvoiceDetailModal';

const STATUSES: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited'];

const ZZPInvoices: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);

  // Invoice detail modal
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(null);

  // Filters
  const [filterStatus, setFilterStatus] = useState('');
  const [filterContactId, setFilterContactId] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  // Copy-last modal
  const { isOpen: isCopyOpen, onOpen: onCopyOpen, onClose: onCopyClose } = useDisclosure();
  const [copyContactId, setCopyContactId] = useState('');
  const [copyLoading, setCopyLoading] = useState(false);

  const loadInvoices = useCallback(async () => {
    try {
      setLoading(true);
      const filters: InvoiceFilters = {};
      if (filterStatus) filters.status = filterStatus as InvoiceStatus;
      if (filterContactId) filters.contact_id = Number(filterContactId);
      if (filterDateFrom) filters.date_from = filterDateFrom;
      if (filterDateTo) filters.date_to = filterDateTo;
      const resp = await getInvoices(filters);
      if (resp.success) setInvoices(resp.data);
    } catch {
      toast({ title: 'Error loading invoices', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterContactId, filterDateFrom, filterDateTo, toast]);

  useEffect(() => { loadInvoices(); }, [loadInvoices]);
  useEffect(() => {
    getContacts().then(resp => { if (resp.success) setContacts(resp.data); });
  }, []);

  const handleRowClick = (inv: Invoice) => {
    setSelectedInvoiceId(inv.id);
    onDetailOpen();
  };

  const handleNew = () => {
    setSelectedInvoiceId(null);
    onDetailOpen();
  };

  const handleDetailSaved = () => {
    loadInvoices();
  };

  const handleDetailClose = () => {
    onDetailClose();
    setSelectedInvoiceId(null);
  };

  const handleExport = () => {
    const csvRows = [
      ['Invoice Number', 'Contact', 'Date', 'Due Date', 'Status', 'Total'].join(','),
      ...invoices.map(inv =>
        [inv.invoice_number, inv.contact?.company_name || '', inv.invoice_date,
         inv.due_date, inv.status, inv.grand_total.toFixed(2)].join(',')
      ),
    ];
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `invoices_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyLast = async () => {
    if (!copyContactId) return;
    try {
      setCopyLoading(true);
      const resp = await copyLastInvoice(Number(copyContactId));
      if (resp.success) {
        toast({ title: t('invoices.copyLastSuccess'), status: 'success' });
        onCopyClose();
        setCopyContactId('');
        loadInvoices();
        // Open the newly created draft in the detail modal
        if (resp.data?.id) {
          setSelectedInvoiceId(resp.data.id);
          onDetailOpen();
        }
      } else {
        toast({ title: resp.error || t('invoices.copyLastNoInvoice'), status: 'warning' });
      }
    } catch {
      toast({ title: t('invoices.copyLastNoInvoice'), status: 'error' });
    } finally {
      setCopyLoading(false);
    }
  };

  const formatCurrency = (amount: number, currency = 'EUR') =>
    new Intl.NumberFormat('nl-NL', { style: 'currency', currency }).format(amount);

  return (
    <Box p={6}>
      {/* Header: title + primary actions */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('invoices.title')}</Text>
        <HStack spacing={2}>
          <Button leftIcon={<CopyIcon />} size="sm" variant="outline" colorScheme="gray"
            color="white" onClick={onCopyOpen}>
            {t('invoices.copyLast')}
          </Button>
          <Button leftIcon={<DownloadIcon />} size="sm" variant="outline" colorScheme="gray"
            color="white" onClick={handleExport} isDisabled={invoices.length === 0}>
            {t('invoices.export')}
          </Button>
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
            {t('invoices.newInvoice')}
          </Button>
        </HStack>
      </Flex>

      {/* Filters */}
      <Flex wrap="wrap" gap={2} mb={4} align="center">
        <Select size="sm" w="160px" bg="gray.700" color="white" borderColor="gray.600"
          value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          placeholder={t('invoices.allStatuses')}>
          {STATUSES.map(s => (
            <option key={s} value={s}>{t(`invoices.status.${s}`, s)}</option>
          ))}
        </Select>
        <Select size="sm" w="200px" bg="gray.700" color="white" borderColor="gray.600"
          value={filterContactId} onChange={e => setFilterContactId(e.target.value)}
          placeholder={t('invoices.allContacts')}>
          {contacts.map(c => (
            <option key={c.id} value={c.id}>{c.company_name} ({c.client_id})</option>
          ))}
        </Select>
        <Input type="date" size="sm" w="150px" bg="gray.700" color="white" borderColor="gray.600"
          value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)}
          placeholder={t('invoices.dateFrom')} aria-label={t('invoices.dateFrom')} />
        <Input type="date" size="sm" w="150px" bg="gray.700" color="white" borderColor="gray.600"
          value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)}
          placeholder={t('invoices.dateTo')} aria-label={t('invoices.dateTo')} />
      </Flex>

      {/* Table */}
      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <Th color="gray.400">{t('invoices.invoiceNumber')}</Th>
                <Th color="gray.400">{t('invoices.contact')}</Th>
                <Th color="gray.400">{t('invoices.invoiceDate')}</Th>
                <Th color="gray.400" display={{ base: 'none', md: 'table-cell' }}>{t('invoices.dueDate')}</Th>
                <Th color="gray.400">Status</Th>
                <Th color="gray.400" isNumeric>{t('invoices.grandTotal')}</Th>
              </Tr>
            </Thead>
            <Tbody>
              {invoices.map(inv => (
                <Tr key={inv.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(inv)}>
                  <Td>{inv.invoice_number}</Td>
                  <Td>{inv.contact?.company_name || '-'}</Td>
                  <Td>{inv.invoice_date}</Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>{inv.due_date}</Td>
                  <Td><InvoiceStatusBadge status={inv.status} /></Td>
                  <Td isNumeric>{formatCurrency(inv.grand_total, inv.currency)}</Td>
                </Tr>
              ))}
              {invoices.length === 0 && (
                <Tr><Td colSpan={6}><Text color="gray.500">{t('common.noData')}</Text></Td></Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      {/* Copy Last Invoice modal — select contact */}
      <Modal isOpen={isCopyOpen} onClose={onCopyClose} isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{t('invoices.copyLast')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <Text fontSize="sm" color="gray.400">{t('invoices.selectContact')}</Text>
              <Select bg="gray.700" borderColor="gray.600"
                value={copyContactId} onChange={e => setCopyContactId(e.target.value)}
                placeholder="—">
                {contacts.map(c => (
                  <option key={c.id} value={c.id}>{c.company_name} ({c.client_id})</option>
                ))}
              </Select>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onCopyClose}>{t('common.cancel')}</Button>
            <Button colorScheme="orange" onClick={handleCopyLast}
              isLoading={copyLoading} isDisabled={!copyContactId}>
              {t('invoices.copyLast')}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Invoice detail modal — view/edit/create */}
      <InvoiceDetailModal
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        invoiceId={selectedInvoiceId}
        onSaved={handleDetailSaved}
      />
    </Box>
  );
};

export default ZZPInvoices;
