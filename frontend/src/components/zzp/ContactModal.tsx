/**
 * Contact CRUD modal — Formik form with field visibility via useFieldConfig.
 * Follows ui-patterns.md: Cancel (ghost) left, Save (orange) right.
 * Reference: .kiro/steering/ui-patterns.md, .kiro/specs/zzp-module/design.md §6.3
 */

import React, { useState, useEffect } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, IconButton, HStack, VStack, Table, Thead, Tbody,
  Tr, Th, Td, Text, useToast, useDisclosure, Badge,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon, EmailIcon } from '@chakra-ui/icons';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { Contact, ContactEmail } from '../../types/zzp';
import { useFieldConfig } from '../../hooks/useFieldConfig';
import { createContact, updateContact } from '../../services/contactService';

interface ContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  contact: Contact | null;
  onSaved: () => void;
}

export const ContactModal: React.FC<ContactModalProps> = ({
  isOpen, onClose, contact, onSaved,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isVisible, isRequired, loading: configLoading } = useFieldConfig('contacts');
  const [emails, setEmails] = useState<Partial<ContactEmail>[]>([]);
  const { isOpen: isEmailOpen, onOpen: onEmailOpen, onClose: onEmailClose } = useDisclosure();
  const isEdit = !!contact;

  useEffect(() => {
    if (contact) {
      setEmails(contact.emails || []);
    } else {
      setEmails([{ email: '', email_type: 'general', is_primary: true }]);
    }
  }, [contact, isOpen]);

  const initialValues = {
    client_id: contact?.client_id || '',
    contact_type: contact?.contact_type || 'client',
    company_name: contact?.company_name || '',
    contact_person: contact?.contact_person || '',
    street_address: contact?.street_address || '',
    postal_code: contact?.postal_code || '',
    city: contact?.city || '',
    country: contact?.country || 'NL',
    vat_number: contact?.vat_number || '',
    kvk_number: contact?.kvk_number || '',
    phone: contact?.phone || '',
    iban: contact?.iban || '',
  };

  const validationSchema = Yup.object().shape({
    client_id: Yup.string().required(t('contacts.clientId') + ' is required')
      .matches(/^[A-Za-z0-9_-]{1,20}$/, 'Max 20 alphanumeric chars'),
    company_name: Yup.string().required(t('contacts.companyName') + ' is required'),
  });

  const addEmail = () => {
    setEmails([...emails, { email: '', email_type: 'general', is_primary: false }]);
  };
  const removeEmail = (idx: number) => setEmails(emails.filter((_, i) => i !== idx));
  const updateEmail = (idx: number, field: string, value: any) => {
    const updated = [...emails];
    updated[idx] = { ...updated[idx], [field]: value };
    setEmails(updated);
  };

  const handleSubmit = async (values: typeof initialValues, { setSubmitting }: any) => {
    try {
      const data: any = { ...values, emails };
      const resp = isEdit
        ? await updateContact(contact!.id, data)
        : await createContact(data);
      if (resp.success) {
        toast({ title: isEdit ? 'Contact updated' : 'Contact created', status: 'success' });
        onSaved();
      } else {
        toast({ title: resp.error, status: 'error' });
      }
    } catch (err: any) {
      toast({ title: err.message || 'Error', status: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const renderField = (name: string, label: string, type = 'text') => {
    if (!isVisible(name)) return null;
    return (
      <FormControl isRequired={isRequired(name)}>
        <FormLabel color="gray.300" fontSize="sm">{label}</FormLabel>
        <Field as={Input} name={name} type={type} size="sm" bg="gray.700"
          color="white" borderColor="gray.600" />
      </FormControl>
    );
  };

  if (configLoading) return null;

  return (
    <>
    <Modal isOpen={isOpen} onClose={onClose} size="xl" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{isEdit ? contact?.company_name : t('contacts.newContact')}</ModalHeader>
        <ModalCloseButton />
        <Formik initialValues={initialValues} validationSchema={validationSchema}
          onSubmit={handleSubmit} enableReinitialize>
          {({ isSubmitting }) => (
            <Form>
              <ModalBody maxH="70vh" overflowY="auto">
                <VStack spacing={3}>
                  {renderField('client_id', t('contacts.clientId'))}
                  {isVisible('contact_type') && (
                    <FormControl isRequired={isRequired('contact_type')}>
                      <FormLabel color="gray.300" fontSize="sm">Type</FormLabel>
                      <Field as={Select} name="contact_type" size="sm" bg="gray.700"
                        color="white" borderColor="gray.600">
                        <option value="client">{t('contacts.type.client')}</option>
                        <option value="supplier">{t('contacts.type.supplier')}</option>
                        <option value="both">{t('contacts.type.both')}</option>
                        <option value="other">{t('contacts.type.other')}</option>
                      </Field>
                    </FormControl>
                  )}
                  {renderField('company_name', t('contacts.companyName'))}
                  {renderField('contact_person', t('contacts.contactPerson'))}
                  {renderField('street_address', t('contacts.streetAddress'))}
                  <HStack w="full">
                    {isVisible('postal_code') && (
                      <FormControl flex={1}>
                        <FormLabel color="gray.300" fontSize="sm">{t('contacts.postalCode')}</FormLabel>
                        <Field as={Input} name="postal_code" size="sm" bg="gray.700"
                          color="white" borderColor="gray.600" />
                      </FormControl>
                    )}
                    {isVisible('city') && (
                      <FormControl flex={2}>
                        <FormLabel color="gray.300" fontSize="sm">{t('contacts.city')}</FormLabel>
                        <Field as={Input} name="city" size="sm" bg="gray.700"
                          color="white" borderColor="gray.600" />
                      </FormControl>
                    )}
                  </HStack>
                  {renderField('country', t('contacts.country'))}
                  {renderField('vat_number', t('contacts.vatNumber'))}
                  {renderField('kvk_number', t('contacts.kvkNumber'))}
                  {renderField('phone', t('contacts.phone'))}
                  {renderField('iban', t('contacts.iban'))}

                  {/* Email addresses — clickable link opens sub-modal */}
                  {isVisible('emails') && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      w="full"
                      leftIcon={<EmailIcon />}
                      colorScheme="gray"
                      color="gray.300"
                      borderColor="gray.600"
                      justifyContent="space-between"
                      onClick={onEmailOpen}
                    >
                      <HStack spacing={2}>
                        <Text>{t('contacts.emails')}</Text>
                        <Badge colorScheme="orange" variant="solid" fontSize="xs">
                          {emails.filter(e => e.email).length}
                        </Badge>
                      </HStack>
                    </Button>
                  )}
                </VStack>
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={onClose}>{t('common.cancel')}</Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  {t('common.save')}
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>

    {/* Email management sub-modal */}
    <Modal isOpen={isEmailOpen} onClose={onEmailClose} size="md" isCentered>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>{t('contacts.emails')}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={3} align="stretch">
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="gray.400">Email</Th>
                  <Th color="gray.400">Type</Th>
                  <Th color="gray.400">Primary</Th>
                  <Th w="40px" />
                </Tr>
              </Thead>
              <Tbody>
                {emails.map((em, idx) => (
                  <Tr key={idx}>
                    <Td>
                      <Input size="sm" bg="gray.700" color="white" borderColor="gray.600"
                        placeholder="email@example.com"
                        value={em.email || ''} onChange={e => updateEmail(idx, 'email', e.target.value)} />
                    </Td>
                    <Td>
                      <Select size="sm" bg="gray.700" color="white" borderColor="gray.600"
                        value={em.email_type || 'general'}
                        onChange={e => updateEmail(idx, 'email_type', e.target.value)}>
                        <option value="general">General</option>
                        <option value="invoice">Invoice</option>
                        <option value="other">Other</option>
                      </Select>
                    </Td>
                    <Td textAlign="center">
                      <input type="checkbox" checked={em.is_primary || false}
                        onChange={e => updateEmail(idx, 'is_primary', e.target.checked)} />
                    </Td>
                    <Td>
                      <IconButton aria-label="Remove" icon={<DeleteIcon />} size="xs"
                        variant="ghost" colorScheme="red" onClick={() => removeEmail(idx)} />
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
            <Button size="sm" leftIcon={<AddIcon />} variant="outline" colorScheme="orange"
              onClick={addEmail}>
              {t('contacts.addEmail', 'Add email')}
            </Button>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button colorScheme="orange" onClick={onEmailClose}>
            {t('common.confirm', 'Done')}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
    </>
  );
};
