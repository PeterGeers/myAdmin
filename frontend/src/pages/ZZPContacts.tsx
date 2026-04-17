/**
 * ZZP Contacts page — Chakra Table with row-click modal for CRUD.
 * Follows BankingProcessor pattern: no row buttons, row-click opens modal.
 * Reference: .kiro/steering/ui-patterns.md, .kiro/specs/zzp-module/design.md §6.2
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Select, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Contact, ContactType } from '../types/zzp';
import { getContacts, getContactTypes } from '../services/contactService';
import { ContactModal } from '../components/zzp/ContactModal';

const TYPE_COLORS: Record<ContactType, string> = {
  client: 'blue', supplier: 'orange', both: 'green', other: 'gray',
};

const ZZPContacts: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactTypes, setContactTypes] = useState<string[]>([]);
  const [filterType, setFilterType] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Contact | null>(null);

  const loadContacts = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getContacts(filterType || undefined);
      if (resp.success) setContacts(resp.data);
    } catch {
      toast({ title: 'Error loading contacts', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [filterType, toast]);

  useEffect(() => { loadContacts(); }, [loadContacts]);
  useEffect(() => {
    getContactTypes().then(resp => { if (resp.success) setContactTypes(resp.data); });
  }, []);

  const handleRowClick = (contact: Contact) => { setSelected(contact); onOpen(); };
  const handleNew = () => { setSelected(null); onOpen(); };
  const handleSaved = () => { onClose(); loadContacts(); };

  return (
    <Box p={6}>
      {/* Page header: title left, primary actions right */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('contacts.title')}</Text>
        <Flex gap={2} align="center">
          <Select size="sm" w="180px" bg="gray.700" color="white" borderColor="gray.600"
            value={filterType} onChange={e => setFilterType(e.target.value)} placeholder="—">
            {contactTypes.map(ct => (
              <option key={ct} value={ct}>{t(`contacts.type.${ct}`, ct)}</option>
            ))}
          </Select>
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
            {t('contacts.newContact')}
          </Button>
        </Flex>
      </Flex>

      {/* Table */}
      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <Th color="gray.400">{t('contacts.clientId')}</Th>
                <Th color="gray.400">{t('contacts.companyName')}</Th>
                <Th color="gray.400">Type</Th>
                <Th color="gray.400" display={{ base: 'none', md: 'table-cell' }}>{t('contacts.contactPerson')}</Th>
                <Th color="gray.400" display={{ base: 'none', md: 'table-cell' }}>{t('contacts.city')}</Th>
                <Th color="gray.400" display={{ base: 'none', lg: 'table-cell' }}>{t('contacts.phone')}</Th>
              </Tr>
            </Thead>
            <Tbody>
              {contacts.map(c => (
                <Tr key={c.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(c)}>
                  <Td>{c.client_id}</Td>
                  <Td>{c.company_name}</Td>
                  <Td>
                    <Badge colorScheme={TYPE_COLORS[c.contact_type] || 'gray'} variant="subtle">
                      {t(`contacts.type.${c.contact_type}`, c.contact_type)}
                    </Badge>
                  </Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>{c.contact_person || '-'}</Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>{c.city || '-'}</Td>
                  <Td display={{ base: 'none', lg: 'table-cell' }}>{c.phone || '-'}</Td>
                </Tr>
              ))}
              {contacts.length === 0 && (
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
