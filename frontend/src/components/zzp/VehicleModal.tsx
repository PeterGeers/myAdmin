/**
 * Vehicle CRUD modal — Formik form with Yup validation for creating/editing vehicles.
 * Follows TripModal pattern: Cancel (ghost) left, Save (orange) right.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.1
 */

import React from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, FormControl, FormLabel,
  Input, Select, VStack, HStack, Text, useToast,
  FormErrorMessage,
} from '@chakra-ui/react';
import { Formik, Form, Field } from 'formik';
import * as Yup from 'yup';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { createVehicle, updateVehicle } from '../../services/vehicleService';
import type { Vehicle } from '../../types/zzpTrips';

/* ─── Types ─── */

interface VehicleModalProps {
  isOpen: boolean;
  onClose: () => void;
  vehicle: Vehicle | null; // null = create mode, Vehicle = edit mode
  onSaved: () => void;
}

interface VehicleFormValues {
  license_plate: string;
  make: string;
  model: string;
  year_built: string;
  vin: string;
  vehicle_type: string;
  odometer_unit: string;
  owner_lease_company: string;
  start_odometer: string;
  start_date: string;
}

/* ─── Constants ─── */

const VEHICLE_TYPES = [
  { value: 'private_for_business', label: 'Privé voor zakelijk gebruik' },
  { value: 'business', label: 'Zakelijk voertuig' },
];

const ODOMETER_UNITS = [
  { value: 'km', label: 'Kilometer (km)' },
  { value: 'miles', label: 'Mijlen (miles)' },
];

/* ─── Component ─── */

export const VehicleModal: React.FC<VehicleModalProps> = ({
  isOpen, onClose, vehicle, onSaved,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();

  const isEdit = !!vehicle;

  const initialValues: VehicleFormValues = {
    license_plate: vehicle?.license_plate || '',
    make: vehicle?.make || '',
    model: vehicle?.model || '',
    year_built: vehicle?.year_built?.toString() || '',
    vin: vehicle?.vin || '',
    vehicle_type: vehicle?.vehicle_type || '',
    odometer_unit: vehicle?.odometer_unit || 'km',
    owner_lease_company: vehicle?.owner_lease_company || '',
    start_odometer: vehicle?.start_odometer?.toString() || '',
    start_date: vehicle?.start_date || new Date().toISOString().slice(0, 10),
  };

  const validationSchema = Yup.object().shape({
    license_plate: Yup.string().required('Kenteken is verplicht'),
    vehicle_type: Yup.string().required('Type voertuig is verplicht'),
    start_odometer: Yup.number()
      .required('Start km-stand is verplicht')
      .min(0, 'Moet 0 of hoger zijn')
      .integer('Moet een geheel getal zijn'),
    start_date: Yup.string().required('Startdatum is verplicht'),
    year_built: Yup.number()
      .nullable()
      .transform((value, originalValue) => (originalValue === '' ? null : value))
      .min(1900, 'Ongeldig bouwjaar')
      .max(new Date().getFullYear() + 1, 'Ongeldig bouwjaar'),
  });

  const handleSubmit = async (values: VehicleFormValues, { setSubmitting }: any) => {
    try {
      const data: Partial<Vehicle> = {
        license_plate: values.license_plate.trim(),
        make: values.make.trim() || null,
        model: values.model.trim() || null,
        year_built: values.year_built ? Number(values.year_built) : null,
        vin: values.vin.trim() || null,
        vehicle_type: values.vehicle_type as Vehicle['vehicle_type'],
        odometer_unit: values.odometer_unit as Vehicle['odometer_unit'],
        owner_lease_company: values.owner_lease_company.trim() || null,
        start_odometer: Number(values.start_odometer),
        start_date: values.start_date,
      };

      let resp;
      if (isEdit) {
        resp = await updateVehicle(vehicle!.id, data);
      } else {
        resp = await createVehicle(data);
      }

      if (resp.success) {
        toast({
          title: isEdit ? 'Voertuig bijgewerkt' : 'Voertuig aangemaakt',
          status: 'success',
          duration: 3000,
        });
        onSaved();
      } else {
        toast({
          title: (resp as any).error || 'Fout bij opslaan',
          status: 'error',
          duration: 3000,
        });
      }
    } catch (err: any) {
      toast({ title: err.message || 'Fout bij opslaan', status: 'error', duration: 3000 });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" closeOnOverlayClick={false}>
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader>
          {isEdit ? `Voertuig bewerken — ${vehicle!.license_plate}` : 'Nieuw voertuig'}
        </ModalHeader>
        <ModalCloseButton />
        <Formik
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
          enableReinitialize
        >
          {({ isSubmitting, errors, touched }) => (
            <Form>
              <ModalBody>
                <VStack spacing={3}>
                  {/* License plate + Vehicle type */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.license_plate && !!touched.license_plate} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Kenteken</FormLabel>
                      <Field as={Input} name="license_plate" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600"
                        placeholder="XX-999-XX" />
                      <FormErrorMessage>{errors.license_plate}</FormErrorMessage>
                    </FormControl>
                    <FormControl isRequired isInvalid={!!errors.vehicle_type && !!touched.vehicle_type} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Type voertuig</FormLabel>
                      <Field as={Select} name="vehicle_type" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" placeholder="—">
                        {VEHICLE_TYPES.map(vt => (
                          <option key={vt.value} value={vt.value}>{vt.label}</option>
                        ))}
                      </Field>
                      <FormErrorMessage>{errors.vehicle_type}</FormErrorMessage>
                    </FormControl>
                  </HStack>

                  {/* Make + Model */}
                  <HStack w="full" spacing={3}>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Merk</FormLabel>
                      <Field as={Input} name="make" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Model/Type</FormLabel>
                      <Field as={Input} name="model" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                  </HStack>

                  {/* Year built + VIN */}
                  <HStack w="full" spacing={3}>
                    <FormControl isInvalid={!!errors.year_built && !!touched.year_built} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Bouwjaar</FormLabel>
                      <Field as={Input} name="year_built" type="number" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.year_built}</FormErrorMessage>
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">VIN/Chassisnummer</FormLabel>
                      <Field as={Input} name="vin" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                  </HStack>

                  {/* Start odometer + Odometer unit */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.start_odometer && !!touched.start_odometer} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Start km-stand</FormLabel>
                      <Field as={Input} name="start_odometer" type="number" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600"
                        isDisabled={isEdit} />
                      {isEdit && (
                        <Text fontSize="xs" color="gray.500" mt={1}>
                          Kan niet worden gewijzigd na aanmaken
                        </Text>
                      )}
                      <FormErrorMessage>{errors.start_odometer}</FormErrorMessage>
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Eenheid</FormLabel>
                      <Field as={Select} name="odometer_unit" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600">
                        {ODOMETER_UNITS.map(u => (
                          <option key={u.value} value={u.value}>{u.label}</option>
                        ))}
                      </Field>
                    </FormControl>
                  </HStack>

                  {/* Start date + Owner/Lease */}
                  <HStack w="full" spacing={3}>
                    <FormControl isRequired isInvalid={!!errors.start_date && !!touched.start_date} flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Startdatum</FormLabel>
                      <Field as={Input} name="start_date" type="date" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                      <FormErrorMessage>{errors.start_date}</FormErrorMessage>
                    </FormControl>
                    <FormControl flex={1}>
                      <FormLabel color="gray.300" fontSize="sm">Eigenaar/Lease</FormLabel>
                      <Field as={Input} name="owner_lease_company" size="sm"
                        bg="gray.700" color="white" borderColor="gray.600" />
                    </FormControl>
                  </HStack>
                </VStack>
              </ModalBody>
              <ModalFooter>
                <Button variant="ghost" mr={3} onClick={onClose}>Annuleren</Button>
                <Button colorScheme="orange" type="submit" isLoading={isSubmitting}>
                  Opslaan
                </Button>
              </ModalFooter>
            </Form>
          )}
        </Formik>
      </ModalContent>
    </Modal>
  );
};
