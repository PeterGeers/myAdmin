/**
 * Time Entry CRUD modal — Formik form with field visibility via useFieldConfig.
 * Follows ContactModal pattern: Cancel (ghost) left, Save (orange) right.
 * Reference: .kiro/specs/zzp-module/design.md §6.2
 */

import React, { useState, useEffect } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, Switch, VStack, HStack, Text, useToast,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { TimeEntry, Contact, Product } from '../../types/zzp';
import { useFieldConfig } from '../../hooks/useFieldConfig';
import { createTimeEntry, updateTimeEntry, deleteTimeEntry } from '../../services/timeTrackingService';
import { getContacts } from '../../services/contactService';
import { getProducts } from '../../services/productService';

interface TimeEntryModalProps {
  isOpen: boolean;
  onClose: () => void;
  entry: TimeEntry | null;
  onSaved: () => void;
}

export const TimeEntryModal: React.FC<TimeEntryModalProps> = ({
  isOpen, onClose, entry, onSaved,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isVisible, isRequired, loading: configLoading } = useFieldConfig('time_entries');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const isEdit = !!entry;
  const isBilled = entry?.is_billed === true;

  useEffect(() => {
    if (isOpen) {
      getContacts().then(resp => { if (resp.success) setContacts(resp.data); });
      getProducts().then(resp => { if (resp.success) setProducts(resp.data); });
    }
  }, [isOpen]);

  const initialValues = {
    contact_id: entry?.contact_id?.toString() || '',
    product_id: entry?.product_id?.toString() || '',
    entry_date: entry?.entry_date || new Date().toISOString().slice(0, 10),
    hours: entry?.hours?.toString() || '',
    hourly_rate: entry?.hourly_rate?.toString() || '',
    project_name: entry?.project_name || '',
    description: entry?.description || '',
    is_billable: entry?.is_billable ?? true,
  };

  const validationSchema = Yup.object().shape({
    contact_id: Yup.string().required('Contact is required'),
    entry_date: Yup.string().required('Date is required'),
    hours: Yup.number().required('Hours is required').positive('Must be positive'),
    hourly_rate: Yup.number().required('Rate is required').min(0, 'Must be >= 0'),
  });

  const handleSubmit = async (values: typeof initialValues, { setSubmitting }: any) => {
    try {
      const data: any = {
        contact_id: Number(values.contact_id),
        entry_date: values.entry_date,
        hours: Number(values.hours),
        hourly_rate: Number(values.hourly_rate),
        is_billable: values.is_billable,
      };
      if (values.product_id) data.product_id = Number(values.product_id);
      if (values.project_name) data.project_name = values.project_name;
      if (values.description) data.description = values.description;

      const resp = isEdit
        ? await updateTimeEntry(entry!.id, data)
        : await createTimeEntry(data);
      if (resp.success) {
        toast({ title: isEdit ? 'Entry updated' : 'Entry created', status: 'success' });
        onSaved();
      } else {
        toast({ title: resp.error || 'Error', status: 'error' });
      }
    } catch (err: any) {
      toast({ title: err.message || 'Error', status: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!entry) return;
    try {
      const resp = await deleteTimeEntry(entry.id);
      if (resp.success) {
        toast({ title: 'Entry deleted', status: 'success' });
        onSaved();
      } else {
        toast({ title: resp.error || 'Error', status: 'error' });
      }
    } catch (err: any) {
      toast({ title: err.message || 'Error', status: 'error' });
    }
  };

  if (configLoading) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>
          {isEdit ? `${entry?.contact?.company_name || ''} — ${entry?.entry_date}` : t('timeTracking.newEntry')}
        </ModalHeader>
        <ModalCloseButton />
        {isBilled ? (
          <ModalBody>
            <Text color="orange.300" mb={4}>{t('timeTracking.billedProtected')}</Text>
            <VStack spacing={3} align="stretch">
              <Text fontSize="sm" color="gray.400">{t('timeTracking.contact')}: {entry?.contact?.company_name}</Text>
              <Text fontSize="sm" color="gray.400">{t('timeTracking.date')}: {entry?.entry_date}</Text>
              <Text fontSize="sm" color="gray.400">{t('timeTracking.hours')}: {entry?.hours}</Text>
              <Text fontSize="sm" color="gray.400">{t('timeTracking.rate')}: € {entry?.hourly_rate?.toFixed(2)}</Text>
              <Text fontSize="sm" color="gray.400">{t('timeTracking.total')}: € {((entry?.hours || 0) * (entry?.hourly_rate || 0)).toFixed(2)}</Text>
              {entry?.project_name && <Text fontSize="sm" color="gray.400">{t('timeTracking.project')}: {entry.project_name}</Text>}
              {entry?.description && <Text fontSize="sm" color="gray.400">{t('timeTracking.description')}: {entry.description}</Text>}
            </VStack>
          </ModalBody>
        ) : (
          <Formik initialValues={initialValues} validationSchema={validationSchema}
            onSubmit={handleSubmit} enableReinitialize>
            {({ isSubmitting, values, setFieldValue }) => (
              <Form>
                <ModalBody>
                  <VStack spacing={3}>
                    {/* Contact — always visible, required */}
                    {isVisible('contact_id') && (
                      <FormControl isRequired={isRequired('contact_id')}>
                        <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.contact')}</FormLabel>
                        <Field as={Select} name="contact_id" size="sm" bg="gray.700"
                          color="white" borderColor="gray.600" placeholder="—">
                          {contacts.map(c => (
                            <option key={c.id} value={c.id}>{c.company_name} ({c.client_id})</option>
                          ))}
                        </Field>
                      </FormControl>
                    )}

                    {/* Date + Hours on same row */}
                    <HStack w="full" spacing={3}>
                      {isVisible('entry_date') && (
                        <FormControl isRequired={isRequired('entry_date')} flex={1}>
                          <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.date')}</FormLabel>
                          <Field as={Input} name="entry_date" type="date" size="sm" bg="gray.700"
                            color="white" borderColor="gray.600" />
                        </FormControl>
                      )}
                      {isVisible('hours') && (
                        <FormControl isRequired={isRequired('hours')} flex={1}>
                          <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.hours')}</FormLabel>
                          <Field as={Input} name="hours" type="number" step="0.25" size="sm"
                            bg="gray.700" color="white" borderColor="gray.600" />
                        </FormControl>
                      )}
                    </HStack>

                    {/* Rate */}
                    {isVisible('hourly_rate') && (
                      <FormControl isRequired={isRequired('hourly_rate')}>
                        <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.hourlyRate')}</FormLabel>
                        <Field as={Input} name="hourly_rate" type="number" step="0.01" size="sm"
                          bg="gray.700" color="white" borderColor="gray.600" />
                      </FormControl>
                    )}

                    {/* Product dropdown */}
                    {isVisible('product_id') && (
                      <FormControl>
                        <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.product')}</FormLabel>
                        <Select name="product_id" size="sm" bg="gray.700" color="white"
                          borderColor="gray.600" placeholder="—"
                          value={values.product_id}
                          onChange={e => {
                            const pid = e.target.value;
                            setFieldValue('product_id', pid);
                            // Auto-fill rate from product
                            if (pid) {
                              const prod = products.find(p => p.id === Number(pid));
                              if (prod && !values.hourly_rate) {
                                setFieldValue('hourly_rate', prod.unit_price.toString());
                              }
                            }
                          }}>
                          {products.map(p => (
                            <option key={p.id} value={p.id}>{p.name} ({p.product_code})</option>
                          ))}
                        </Select>
                      </FormControl>
                    )}

                    {/* Project */}
                    {isVisible('project_name') && (
                      <FormControl>
                        <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.project')}</FormLabel>
                        <Field as={Input} name="project_name" size="sm" bg="gray.700"
                          color="white" borderColor="gray.600" />
                      </FormControl>
                    )}

                    {/* Description */}
                    {isVisible('description') && (
                      <FormControl>
                        <FormLabel color="gray.300" fontSize="sm">{t('timeTracking.description')}</FormLabel>
                        <Field as={Input} name="description" size="sm" bg="gray.700"
                          color="white" borderColor="gray.600" />
                      </FormControl>
                    )}

                    {/* Billable toggle */}
                    {isVisible('is_billable') && (
                      <FormControl display="flex" alignItems="center">
                        <FormLabel color="gray.300" fontSize="sm" mb={0}>{t('timeTracking.billable')}</FormLabel>
                        <Switch isChecked={values.is_billable}
                          onChange={e => setFieldValue('is_billable', e.target.checked)}
                          colorScheme="orange" />
                      </FormControl>
                    )}
                  </VStack>
                </ModalBody>
                <ModalFooter>
                  {isEdit && (
                    <Button colorScheme="red" variant="ghost" mr="auto" onClick={handleDelete}>
                      {t('common.delete')}
                    </Button>
                  )}
                  <Button variant="ghost" mr={3} onClick={onClose}>{t('common.cancel')}</Button>
                  <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                    {t('common.save')}
                  </Button>
                </ModalFooter>
              </Form>
            )}
          </Formik>
        )}
        {isBilled && (
          <ModalFooter>
            <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          </ModalFooter>
        )}
      </ModalContent>
    </Modal>
  );
};
