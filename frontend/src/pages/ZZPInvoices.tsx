/**
 * ZZP Invoices page — Chakra Table with filters and header actions.
 * Follows BankingProcessor pattern: row-click opens detail, no inline buttons.
 * Reference: .kiro/specs/zzp-module/design.md §4.3, §6.2
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Input,
  Table, Thead, Tbody, Tr, Th, Td, HStack, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack, Select,
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

  // Filters — client-side, one search input per table column
  const [fInvoiceNumber, setFInvoiceNumber] = useState('');
  const [fClientId, setFClientId] = useState('');
  const [fInvoiceDate, setFInvoiceDate] = useState('');
  const [fDueDate, setFDueDate] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [fTotal, setFTotal] = useState('');

  // Copy-last modal
  const { isOpen: isCopyOpen, onOpen: onCopyOpen, onClose: onCopyClose } = useDisclosure();
  const [copyContactId, setCopyContactId] = useState('');
  const [copyLoading, setCopyLoading] = useState(false);

  const loadInvoices = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getInvoices({});
      if (resp.success) setInvoices(resp.data);
    } catch {
      toast({ title: 'Error loading invoices', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadInvoices(); }, [loadInvoices]);
  useEffect(() => {
    getContacts().then(resp => { if (resp.success) setContacts(resp.data); });
  }, []);

  const formatCurrency = (amount: number, cur = 'EUR') => {
    const code = (cur || 'EUR').trim().toUpperCase();
    const safeCur = /^[A-Z]{3}$/.test(code) ? code : 'EUR';
    return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: safeCur }).format(amount);
  };

  // Client-side filtered invoices — case-insensitive substring match per column
  const filteredInvoices = useMemo(() => {
    return invoices.filter(inv => {
      if (fInvoiceNumber && !inv.invoice_number.toLowerCase().includes(fInvoiceNumber.toLowerCase())) return false;
      if (fClientId && !(inv.contact?.client_id || '').toLowerCase().includes(fClientId.toLowerCase())) return false;
      if (fInvoiceDate && !(inv.invoice_date || '').includes(fInvoiceDate)) return false;
      if (fDueDate && !(inv.due_date || '').includes(fDueDate)) return false;
      if (fStatus && !inv.status.toLowerCase().includes(fStatus.toLowerCase())) return false;
      if (fTotal && !formatCurrency(inv.grand_total, inv.currency).toLowerCase().includes(fTotal.toLowerCase())) return false;
      return true;
    });
  }, [invoices, fInvoiceNumber, fClientId, fInvoiceDate, fDueDate, fStatus, fTotal]);

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
         inv.due_date, inv.status, Number(inv.grand_total).toFixed(2)].join(',')
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

      {/* Table with column-aligned filter inputs in header */}
      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <Th color="gray.400" pb={1}>{t('invoices.invoiceNumber')}</Th>
                <Th color="gray.400" pb={1}>{t('contacts.clientId', 'Client ID')}</Th>
                <Th color="gray.400" pb={1}>{t('invoices.invoiceDate')}</Th>
                <Th color="gray.400" pb={1} display={{ base: 'none', md: 'table-cell' }}>{t('invoices.dueDate')}</Th>
                <Th color="gray.400" pb={1}>Status</Th>
                <Th color="gray.400" pb={1} isNumeric>{t('invoices.grandTotal')}</Th>
              </Tr>
              <Tr>
                <Th pt={0} pb={2}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fInvoiceNumber} onChange={e => setFInvoiceNumber(e.target.value)} /></Th>
                <Th pt={0} pb={2}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fClientId} onChange={e => setFClientId(e.target.value)} /></Th>
                <Th pt={0} pb={2}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fInvoiceDate} onChange={e => setFInvoiceDate(e.target.value)} /></Th>
                <Th pt={0} pb={2} display={{ base: 'none', md: 'table-cell' }}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fDueDate} onChange={e => setFDueDate(e.target.value)} /></Th>
                <Th pt={0} pb={2}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fStatus} onChange={e => setFStatus(e.target.value)} /></Th>
                <Th pt={0} pb={2}><Input size="xs" bg="gray.700" color="white" borderColor="gray.600" placeholder="Filter..." value={fTotal} onChange={e => setFTotal(e.target.value)} /></Th>
              </Tr>
            </Thead>
            <Tbody>
              {filteredInvoices.map(inv => (
                <Tr key={inv.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(inv)}>
                  <Td>{inv.invoice_number}</Td>
                  <Td>{inv.contact?.client_id || '-'}</Td>
                  <Td>{inv.invoice_date}</Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>{inv.due_date}</Td>
                  <Td><InvoiceStatusBadge status={inv.status} /></Td>
                  <Td isNumeric>{formatCurrency(inv.grand_total, inv.currency)}</Td>
                </Tr>
              ))}
              {filteredInvoices.length === 0 && (
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
