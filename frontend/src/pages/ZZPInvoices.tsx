/**
 * ZZP Invoices page — Chakra Table with filters and header actions.
 * Follows BankingProcessor pattern: row-click opens detail, no inline buttons.
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useFilterableTable + FilterableHeader for inline column text filters + sort
 * Reference: .kiro/specs/zzp-module/design.md §4.3, §6.2
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, HStack, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack, Select,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, CopyIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Invoice, Contact } from '../types/zzp';
import { getInvoices, copyLastInvoice } from '../services/zzpInvoiceService';
import { getContacts } from '../services/contactService';
import { InvoiceStatusBadge } from '../components/zzp/InvoiceStatusBadge';
import { InvoiceDetailModal } from '../components/zzp/InvoiceDetailModal';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';

/** Flat row for filtering — nested contact.client_id promoted to top-level */
interface InvoiceRow extends Invoice {
  client_id: string;
  formatted_total: string;
}

const INITIAL_FILTERS: Record<string, string> = {
  invoice_number: '',
  client_id: '',
  invoice_date: '',
  due_date: '',
  status: '',
  formatted_total: '',
};

const ZZPInvoices: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);

  // Invoice detail modal
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(null);

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

  // Build flat rows with promoted nested fields for filtering
  const invoiceRows: InvoiceRow[] = useMemo(
    () => invoices.map(inv => ({
      ...inv,
      client_id: inv.contact?.client_id || '',
      formatted_total: formatCurrency(inv.grand_total, inv.currency),
    })),
    [invoices],
  );

  // Combined column filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<InvoiceRow>(invoiceRows, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'invoice_date', direction: 'desc' },
  });

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

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  return (
    <Box p={6}>
      {/* Header: title + primary actions */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('invoices.title')}</Text>
        <HStack spacing={2}>
          <Button leftIcon={<CopyIcon />} size="sm" colorScheme="orange"
            onClick={onCopyOpen}>
            {t('invoices.copyLast')}
          </Button>
          <Button leftIcon={<DownloadIcon />} size="sm" colorScheme="orange"
            onClick={handleExport} isDisabled={invoices.length === 0}>
            {t('invoices.export')}
          </Button>
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
            {t('invoices.newInvoice')}
          </Button>
        </HStack>
      </Flex>

      {/* Table with FilterableHeader columns */}
      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('invoices.invoiceNumber')}
                  filterValue={filters.invoice_number}
                  onFilterChange={(v) => setFilter('invoice_number', v)}
                  sortable
                  sortDirection={columnSortDirection('invoice_number')}
                  onSort={() => handleSort('invoice_number')}
                />
                <FilterableHeader
                  label={t('contacts.clientId', 'Client ID')}
                  filterValue={filters.client_id}
                  onFilterChange={(v) => setFilter('client_id', v)}
                  sortable
                  sortDirection={columnSortDirection('client_id')}
                  onSort={() => handleSort('client_id')}
                />
                <FilterableHeader
                  label={t('invoices.invoiceDate')}
                  filterValue={filters.invoice_date}
                  onFilterChange={(v) => setFilter('invoice_date', v)}
                  sortable
                  sortDirection={columnSortDirection('invoice_date')}
                  onSort={() => handleSort('invoice_date')}
                />
                <FilterableHeader
                  label={t('invoices.dueDate')}
                  filterValue={filters.due_date}
                  onFilterChange={(v) => setFilter('due_date', v)}
                  sortable
                  sortDirection={columnSortDirection('due_date')}
                  onSort={() => handleSort('due_date')}
                />
                <FilterableHeader
                  label="Status"
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  sortable
                  sortDirection={columnSortDirection('status')}
                  onSort={() => handleSort('status')}
                />
                <FilterableHeader
                  label={t('invoices.grandTotal')}
                  filterValue={filters.formatted_total}
                  onFilterChange={(v) => setFilter('formatted_total', v)}
                  isNumeric
                  sortable
                  sortDirection={columnSortDirection('grand_total')}
                  onSort={() => handleSort('grand_total')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(inv => (
                <Tr key={inv.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(inv)}>
                  <Td>{inv.invoice_number}</Td>
                  <Td>{inv.client_id || '-'}</Td>
                  <Td>{inv.invoice_date}</Td>
                  <Td>{inv.due_date}</Td>
                  <Td><InvoiceStatusBadge status={inv.status} /></Td>
                  <Td isNumeric>{inv.formatted_total}</Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
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
