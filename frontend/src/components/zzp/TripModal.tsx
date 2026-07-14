/**
 * Trip CRUD modal — Formik form with Yup validation for creating/editing trips.
 * Follows TimeEntryModal pattern: Cancel (ghost) left, Save (orange) right.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.2
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, Switch, Textarea, VStack, HStack, Text, useToast,
  FormErrorMessage,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import type { FieldProps } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { createTrip, updateTrip, cancelTrip, getTrips } from '../../services/tripService';
import { getContacts } from '../../services/contactService';
import type { Trip } from '../../types/zzpTrips';
import type { Contact } from '../../types/zzp';

/* ─── Types ─── */

interface TripModalProps {
  isOpen: boolean;
  onClose: () => void;
  trip: Trip | null; // null = create mode, Trip = edit mode
  onSaved: () => void;
  vehicleId: number;
}

interface TripFormValues {
  trip_date: string;
  start_time: string;
  end_time: string;
  start_address: string;
  end_address: string;
  start_odometer: string;
  end_odometer: string;
  trip_category: string;
  trip_purpose: string;
  contact_id: string;
  project_name: string;
  notes: string;
  is_billable: boolean;
  correction_reason: string;
}

/* ─── Constants ─── */

const TRIP_CATEGORIES = ['Zakelijk', 'Privé', 'Woon-werk'];
const TRIP_PURPOSES = [
  'Klantbezoek',
  'Vergadering',
  'Materiaal ophalen',
  'Overig',
];

/* ─── Component ─── */

export const TripModal: React.FC<TripModalProps> = ({
  isOpen, onClose, trip, onSaved, vehicleId,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [lastEndOdometer, setLastEndOdometer] = useState<number | null>(null);

  const isEdit = !!trip;
  const isBilled = trip?.is_billed === true;
  const isCancelled = trip?.is_cancelled === true;
  const isReadOnly = isBilled || isCancelled;
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Load contacts and last odometer on open
  useEffect(() => {
    if (!isOpen) return;
    getContacts().then(resp => {
      if (resp.success) setContacts(resp.data || []);
    });

    // Pre-fill start_odometer with last trip's end_odometer (create mode only)
    if (!trip && vehicleId) {
      getTrips({ vehicle_id: vehicleId, limit: 1 }).then(resp => {
        if (resp.success && resp.data?.length > 0) {
          setLastEndOdometer(resp.data[0].end_odometer);
        }
      });
    }
  }, [isOpen, trip, vehicleId]);

  const initialValues: TripFormValues = {
    trip_date: trip?.trip_date || new Date().toISOString().slice(0, 10),
    start_time: trip?.start_time || '',
    end_time: trip?.end_time || '',
    start_address: trip?.start_address || '',
    end_address: trip?.end_address || '',
    start_odometer: trip?.start_odometer?.toString() || (lastEndOdometer?.toString() || ''),
    end_odometer: trip?.end_odometer?.toString() || '',
    trip_category: trip?.trip_category || '',
    trip_purpose: trip?.trip_purpose || '',
    contact_id: trip?.contact_id?.toString() || '',
    project_name: trip?.project_name || '',
    notes: trip?.notes || '',
    is_billable: trip?.is_billable ?? false,
    correction_reason: '',
  };

  const validationSchema = Yup.object().shape({
    trip_date: Yup.string().required(t('trips.validation.dateRequired')),
    start_address: Yup.string().required(t('trips.validation.startAddressRequired')),
    end_address: Yup.string().required(t('trips.validation.endAddressRequired')),
    start_odometer: Yup.number()
      .required(t('trips.validation.startOdometerRequired'))
      .positive(t('trips.validation.mustBePositive'))
      .integer(t('trips.validation.mustBeInteger')),
    end_odometer: Yup.number()
      .required(t('trips.validation.endOdometerRequired'))
      .positive(t('trips.validation.mustBePositive'))
      .integer(t('trips.validation.mustBeInteger'))
      .when('start_odometer', (startOdometer, schema) => {
        const startVal = Array.isArray(startOdometer) ? startOdometer[0] : startOdometer;
        return startVal
          ? schema.moreThan(Number(startVal), t('trips.validation.endMustBeGreater'))
          : schema;
      }),
    trip_category: Yup.string().required(t('trips.validation.categoryRequired')),
    trip_purpose: Yup.string().required(t('trips.validation.purposeRequired')),
    correction_reason: isEdit
      ? Yup.string().required(t('trips.validation.correctionReasonRequired'))
      : Yup.string(),
  });

  const handleSubmit = async (values: TripFormValues, { setSubmitting }: any) => {
    try {
      const data: any = {
        vehicle_id: vehicleId,
        trip_date: values.trip_date,
        start_address: values.start_address,
        end_address: values.end_address,
        start_odometer: Number(values.start_odometer),
        end_odometer: Number(values.end_odometer),
        trip_category: values.trip_category,
        trip_purpose: values.trip_purpose,
        is_billable: values.is_billable,
      };
      if (values.start_time) data.start_time = values.start_time;
      if (values.end_time) data.end_time = values.end_time;
      if (values.contact_id) data.contact_id = Number(values.contact_id);
      if (values.project_name) data.project_name = values.project_name;
      if (values.notes) data.notes = values.notes;

      let resp;
      if (isEdit) {
        data.correction_reason = values.correction_reason;
        resp = await updateTrip(trip!.id, data);
      } else {
        resp = await createTrip(data);
      }

      if (resp.success) {
        toast({
          title: isEdit ? t('trips.toast.updated') : t('trips.toast.created'),
          status: 'success',
          duration: 3000,
        });
        // Handle gap warnings
        if (resp.warnings && resp.warnings.length > 0) {
          resp.warnings.forEach((w) => {
            toast({
              title: w.message || t('trips.toast.gapWarning'),
              status: 'warning',
              duration: 5000,
              isClosable: true,
            });
          });
        }
        onSaved();
        onClose();
      } else {
        toast({
          title: (resp as any).error || t('trips.toast.error'),
          status: 'error',
          duration: 3000,
        });
      }
    } catch (err: any) {
      toast({ title: err.message || t('trips.toast.error'), status: 'error', duration: 3000 });
    } finally {
      setSubmitting(false);
    }
  };

  /* ─── Cancel (soft-delete) handler ─── */
  const handleCancelTrip = async () => {
    if (!trip || !cancelReason.trim()) {
      toast({ title: t('trips.validation.cancelReasonRequired'), status: 'warning', duration: 3000 });
      return;
    }
    setCancelling(true);
    try {
      const resp = await cancelTrip(trip.id, cancelReason.trim());
      if (resp.success) {
        toast({ title: t('trips.toast.cancelled'), status: 'success', duration: 3000 });
        setShowCancelConfirm(false);
        setCancelReason('');
        onSaved();
        onClose();
      } else {
        toast({ title: resp.error || t('trips.toast.error'), status: 'error', duration: 3000 });
      }
    } catch (err: any) {
      toast({ title: err.message || t('trips.toast.error'), status: 'error', duration: 3000 });
    } finally {
      setCancelling(false);
    }
  };

  /* ─── Read-only view for billed/cancelled trips ─── */
  if (isReadOnly && trip) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} size="xl" closeOnOverlayClick={false}>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{trip.trip_date} — {trip.start_address} → {trip.end_address}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text color="orange.300" mb={4}>
              {isBilled
                ? t('trips.readOnly.billed')
                : t('trips.readOnly.cancelled')}
            </Text>
            <VStack spacing={2} align="stretch">
              <Text fontSize="sm" color="gray.400">{t('trips.labels.date')}: {trip.trip_date}</Text>
              <Text fontSize="sm" color="gray.400">{t('trips.labels.startAddress')}: {trip.start_address}</Text>
              <Text fontSize="sm" color="gray.400">{t('trips.labels.endAddress')}: {trip.end_address}</Text>
              <Text fontSize="sm" color="gray.400">{t('trips.labels.distance')}: {trip.distance_km} km</Text>
              <Text fontSize="sm" color="gray.400">{t('trips.labels.category')}: {trip.trip_category}</Text>
              <Text fontSize="sm" color="gray.400">{t('trips.labels.purpose')}: {trip.trip_purpose}</Text>
              {trip.contact?.company_name && (
                <Text fontSize="sm" color="gray.400">{t('trips.labels.client')}: {trip.contact.company_name}</Text>
              )}
              {trip.project_name && (
                <Text fontSize="sm" color="gray.400">{t('trips.labels.project')}: {trip.project_name}</Text>
              )}
              {trip.notes && (
                <Text fontSize="sm" color="gray.400">{t('trips.labels.notes')}: {trip.notes}</Text>
              )}
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  /* ─── Editable form ─── */
  return (
  <>
    <Modal isOpen={isOpen} onClose={onClose} size="xl" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>
          {isEdit
            ? `${trip!.trip_date} — ${trip!.start_address} → ${trip!.end_address}`
            : t('trips.newTrip')}
        </ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
          enableReinitialize
        >
          {({ isSubmitting, values, setFieldValue, errors, touched }) => (
            <Form>
              <ModalBody>
                <VStack spacing={3}>
                  {/* Date + Times */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.trip_date && !!touched.trip_date} flex={2}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.date')}</FormLabel>
                      <Field as={Input} name="trip_date" type="date" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.trip_date}</FormErrorMessage>
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.startTime')}</FormLabel>
                      <Field as={Input} name="start_time" type="time" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.endTime')}</FormLabel>
                      <Field as={Input} name="end_time" type="time" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                  </HStack>

                  {/* Start / End Address */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.start_address && !!touched.start_address} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.startAddress')}</FormLabel>
                      <Field as={Input} name="start_address" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.start_address}</FormErrorMessage>
                    </FormControl>
                    <FormControl isRequired isInvalid={!!errors.end_address && !!touched.end_address} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.endAddress')}</FormLabel>
                      <Field as={Input} name="end_address" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.end_address}</FormErrorMessage>
                    </FormControl>
                  </HStack>

                  {/* Odometers */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.start_odometer && !!touched.start_odometer} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.startOdometer')}</FormLabel>
                      <Field as={Input} name="start_odometer" type="number" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.start_odometer}</FormErrorMessage>
                    </FormControl>
                    <FormControl isRequired isInvalid={!!errors.end_odometer && !!touched.end_odometer} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.endOdometer')}</FormLabel>
                      <Field as={Input} name="end_odometer" type="number" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.end_odometer}</FormErrorMessage>
                    </FormControl>
                  </HStack>

                  {/* Category + Purpose */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.trip_category && !!touched.trip_category} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.category')}</FormLabel>
                      <Field as={Select} name="trip_category" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" placeholder="—">
                        {TRIP_CATEGORIES.map(cat => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </Field>
                      <FormErrorMessage>{errors.trip_category}</FormErrorMessage>
                    </FormControl>
                    <FormControl isRequired isInvalid={!!errors.trip_purpose && !!touched.trip_purpose} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.purpose')}</FormLabel>
                      <Field as={Select} name="trip_purpose" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" placeholder="—">
                        {TRIP_PURPOSES.map(p => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </Field>
                      <FormErrorMessage>{errors.trip_purpose}</FormErrorMessage>
                    </FormControl>
                  </HStack>

                  {/* Contact + Project */}
                  <HStack w="full" spacing={3}>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.client')}</FormLabel>
                      <Field as={Select} name="contact_id" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" placeholder="—">
                        {contacts.map(c => (
                          <option key={c.id} value={c.id}>{c.company_name}</option>
                        ))}
                      </Field>
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.project')}</FormLabel>
                      <Field as={Input} name="project_name" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                  </HStack>

                  {/* Notes */}
                  <FormControl>
                    <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.notes')}</FormLabel>
                    <Field as={Textarea} name="notes" size="sm" rows={2}
                      bg="gray.700" color="white" borderColor="gray.600" />
                  </FormControl>

                  {/* Billable toggle */}
                  <FormControl display="flex" alignItems="center">
                    <FormLabel color="gray.300" fontSize="sm" mb={0}>{t('trips.labels.billable')}</FormLabel>
                    <Field name="is_billable">
                      {({ field }: FieldProps) => (
                        <Switch
                          isChecked={field.value}
                          onChange={(e) => setFieldValue('is_billable', e.target.checked)}
                          colorScheme="orange"
                        />
                      )}
                    </Field>
                  </FormControl>

                  {/* Correction reason — edit mode only */}
                  {isEdit && (
                    <FormControl isRequired isInvalid={!!errors.correction_reason && !!touched.correction_reason}>
                      <FormLabel color="gray.300" fontSize="sm">{t('trips.labels.correctionReason')}</FormLabel>
                      <Field as={Input} name="correction_reason" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600"
                        placeholder={t('trips.placeholders.correctionReason')} />
                      <FormErrorMessage>{errors.correction_reason}</FormErrorMessage>
                    </FormControl>
                  )}
                </VStack>
              </ModalBody>
              <ModalFooter>
                {isEdit && (
                  <Button
                    colorScheme="red"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowCancelConfirm(true)}
                    mr="auto"
                  >
                    {t('trips.actions.cancelTrip')}
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
      </ModalContent>
    </Modal>

    {/* Cancel Trip Confirmation Dialog */}
    <AlertDialog
      isOpen={showCancelConfirm}
      leastDestructiveRef={cancelRef}
      onClose={() => { setShowCancelConfirm(false); setCancelReason(''); }}
    >
      <AlertDialogOverlay>
        <AlertDialogContent bg="gray.800" color="white">
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            {t('trips.actions.cancelTrip')}
          </AlertDialogHeader>
          <AlertDialogBody>
            <Text mb={3} color="gray.300">
              {t('trips.cancelConfirm.message')}
            </Text>
            <Input
              placeholder={t('trips.placeholders.cancelReason')}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              bg="gray.700"
              borderColor="gray.600"
              color="white"
              _placeholder={{ color: 'gray.400' }}
            />
          </AlertDialogBody>
          <AlertDialogFooter>
            <Button
              ref={cancelRef}
              variant="ghost"
              onClick={() => { setShowCancelConfirm(false); setCancelReason(''); }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              colorScheme="red"
              onClick={handleCancelTrip}
              isLoading={cancelling}
              isDisabled={!cancelReason.trim()}
              ml={3}
            >
              {t('trips.actions.confirmCancel')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  </>
  );
};
