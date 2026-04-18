/**
 * ZZP Contacts page — Chakra Table with row-click modal for CRUD.
 * Follows BankingProcessor pattern: no row buttons, row-click opens modal.
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - FilterPanel + GenericFilter for the type dropdown (server-side filter)
 * - useFilterableTable + FilterableHeader for inline column text filters + sort
 * Reference: .kiro/steering/ui-patterns.md, .kiro/specs/zzp-module/design.md §6.2
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Contact, ContactType } from '../types/zzp';
import { getContacts } from '../services/contactService';
import { ContactModal } from '../components/zzp/ContactModal';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';

const TYPE_COLORS: Record<ContactType, string> = {
  client: 'blue', supplier: 'orange', both: 'green', other: 'gray',
};

const INITIAL_FILTERS: Record<string, string> = {
  client_id: '',
  company_name: '',
  contact_type: '',
  contact_person: '',
  city: '',
  phone: '',
};

const ZZPContacts: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Contact | null>(null);

  // Combined column filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<Contact>(contacts, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'company_name', direction: 'asc' },
  });

  const loadContacts = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getContacts();
      if (resp.success) setContacts(resp.data);
    } catch {
      toast({ title: 'Error loading contacts', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadContacts(); }, [loadContacts]);

  const handleRowClick = (contact: Contact) => { setSelected(contact); onOpen(); };
  const handleNew = () => { setSelected(null); onOpen(); };
  const handleSaved = () => { onClose(); loadContacts(); };

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  return (
    <Box p={6}>
      {/* Page header: title left, primary actions right */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('contacts.title')}</Text>
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
          {t('contacts.newContact')}
        </Button>
      </Flex>

      {/* Table */}
      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('contacts.clientId')}
                  filterValue={filters.client_id}
                  onFilterChange={(v) => setFilter('client_id', v)}
                  sortable
                  sortDirection={columnSortDirection('client_id')}
                  onSort={() => handleSort('client_id')}
                />
                <FilterableHeader
                  label={t('contacts.companyName')}
                  filterValue={filters.company_name}
                  onFilterChange={(v) => setFilter('company_name', v)}
                  sortable
                  sortDirection={columnSortDirection('company_name')}
                  onSort={() => handleSort('company_name')}
                />
                <FilterableHeader
                  label="Type"
                  filterValue={filters.contact_type}
                  onFilterChange={(v) => setFilter('contact_type', v)}
                  sortable
                  sortDirection={columnSortDirection('contact_type')}
                  onSort={() => handleSort('contact_type')}
                />
                <FilterableHeader
                  label={t('contacts.contactPerson')}
                  filterValue={filters.contact_person}
                  onFilterChange={(v) => setFilter('contact_person', v)}
                  sortable
                  sortDirection={columnSortDirection('contact_person')}
                  onSort={() => handleSort('contact_person')}
                />
                <FilterableHeader
                  label={t('contacts.city')}
                  filterValue={filters.city}
                  onFilterChange={(v) => setFilter('city', v)}
                  sortable
                  sortDirection={columnSortDirection('city')}
                  onSort={() => handleSort('city')}
                />
                <FilterableHeader
                  label={t('contacts.phone')}
                  filterValue={filters.phone}
                  onFilterChange={(v) => setFilter('phone', v)}
                  sortable
                  sortDirection={columnSortDirection('phone')}
                  onSort={() => handleSort('phone')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(c => (
                <Tr key={c.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(c)}>
                  <Td>{c.client_id}</Td>
                  <Td>{c.company_name}</Td>
                  <Td>
                    <Badge colorScheme={TYPE_COLORS[c.contact_type] || 'gray'} variant="subtle">
                      {t(`contacts.type.${c.contact_type}`, c.contact_type)}
                    </Badge>
                  </Td>
                  <Td>{c.contact_person || '-'}</Td>
                  <Td>{c.city || '-'}</Td>
                  <Td>{c.phone || '-'}</Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
                <Tr><Td colSpan={6}><Text color="gray.500">{t('common.noData')}</Text></Td></Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      <ContactModal isOpen={isOpen} onClose={onClose}
        contact={selected} onSaved={handleSaved} />
    </Box>
  );
};

export default ZZPContacts;
