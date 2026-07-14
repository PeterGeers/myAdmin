/**
 * ZZP Vehicles (Voertuigen) page — vehicle management for Rittenregistratie.
 * Dark-theme Chakra UI table with create/edit modal and deactivate action.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.1
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Badge, useDisclosure,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { getVehicles, deactivateVehicle } from '../services/vehicleService';
import type { Vehicle } from '../types/zzpTrips';
import { VehicleModal } from '../components/zzp/VehicleModal';

/* ─── Helpers ─── */

/** Format vehicle type for display. */
function formatVehicleType(type: string): string {
  switch (type) {
    case 'private_for_business':
      return 'Privé zakelijk';
    case 'business':
      return 'Zakelijk';
    default:
      return type;
  }
}

/* ─── Main Page ─── */
const ZZPVehicles: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const {
    isOpen: isAlertOpen,
    onOpen: onAlertOpen,
    onClose: onAlertClose,
  } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Data state
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<Vehicle | null>(null);
  const [vehicleToDeactivate, setVehicleToDeactivate] = useState<Vehicle | null>(null);
  const [loading, setLoading] = useState(true);

  // Load vehicles
  const loadVehicles = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getVehicles(false);
      if (resp.success) {
        setVehicles(resp.data || []);
      }
    } catch {
      toast({ title: 'Fout bij laden voertuigen', status: 'error', duration: 3000 });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadVehicles();
  }, [loadVehicles]);

  // Row click → open modal for editing
  const handleRowClick = (vehicle: Vehicle) => {
    setSelectedVehicle(vehicle);
    onOpen();
  };

  // New vehicle button
  const handleNewVehicle = () => {
    setSelectedVehicle(null);
    onOpen();
  };

  // Modal saved callback
  const handleSaved = () => {
    onClose();
    loadVehicles();
  };

  // Deactivate flow
  const handleDeactivateClick = (e: React.MouseEvent, vehicle: Vehicle) => {
    e.stopPropagation();
    setVehicleToDeactivate(vehicle);
    onAlertOpen();
  };

  const handleDeactivateConfirm = async () => {
    if (!vehicleToDeactivate) return;
    try {
      const resp = await deactivateVehicle(vehicleToDeactivate.id);
      if (resp.success) {
        toast({ title: 'Voertuig gedeactiveerd', status: 'success', duration: 3000 });
        loadVehicles();
      } else {
        toast({ title: resp.error || 'Fout bij deactiveren', status: 'error', duration: 3000 });
      }
    } catch {
      toast({ title: 'Fout bij deactiveren', status: 'error', duration: 3000 });
    } finally {
      setVehicleToDeactivate(null);
      onAlertClose();
    }
  };

  return (
    <Box p={4} bg="gray.800" color="white" minH="100vh">
      {/* Header */}
      <Flex justify="space-between" align="center" mb={4} wrap="wrap" gap={2}>
        <Text fontSize="xl" fontWeight="bold">Voertuigen</Text>
        <Button
          colorScheme="orange"
          size="sm"
          leftIcon={<AddIcon />}
          onClick={handleNewVehicle}
        >
          Nieuw voertuig
        </Button>
      </Flex>

      {/* Content */}
      {loading ? (
        <Flex justify="center" py={10}>
          <Spinner color="orange.300" size="lg" />
        </Flex>
      ) : vehicles.length === 0 ? (
        <Box textAlign="center" py={10}>
          <Text color="gray.400">Geen voertuigen gevonden</Text>
        </Box>
      ) : (
        <Box overflowX="auto">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="gray.300">Kenteken</Th>
                <Th color="gray.300">Merk/Model</Th>
                <Th color="gray.300">Type</Th>
                <Th color="gray.300">Bouwjaar</Th>
                <Th color="gray.300" isNumeric>Start km-stand</Th>
                <Th color="gray.300">Status</Th>
                <Th color="gray.300">Actie</Th>
              </Tr>
            </Thead>
            <Tbody>
              {vehicles.map((vehicle) => (
                <Tr
                  key={vehicle.id}
                  cursor="pointer"
                  _hover={{ bg: 'gray.700' }}
                  onClick={() => handleRowClick(vehicle)}
                >
                  <Td fontWeight="medium">{vehicle.license_plate}</Td>
                  <Td>
                    {[vehicle.make, vehicle.model].filter(Boolean).join(' ') || '-'}
                  </Td>
                  <Td>{formatVehicleType(vehicle.vehicle_type)}</Td>
                  <Td>{vehicle.year_built || '-'}</Td>
                  <Td isNumeric>{vehicle.start_odometer.toLocaleString('nl-NL')}</Td>
                  <Td>
                    <Badge colorScheme={vehicle.is_active ? 'green' : 'gray'}>
                      {vehicle.is_active ? 'Actief' : 'Inactief'}
                    </Badge>
                  </Td>
                  <Td onClick={(e) => e.stopPropagation()}>
                    {vehicle.is_active && (
                      <Button
                        size="xs"
                        colorScheme="red"
                        variant="ghost"
                        onClick={(e) => handleDeactivateClick(e, vehicle)}
                      >
                        Deactiveren
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      {/* Vehicle Modal */}
      <VehicleModal
        isOpen={isOpen}
        onClose={onClose}
        vehicle={selectedVehicle}
        onSaved={handleSaved}
      />

      {/* Deactivate Confirmation Dialog */}
      <AlertDialog
        isOpen={isAlertOpen}
        leastDestructiveRef={cancelRef}
        onClose={onAlertClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white">
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Voertuig deactiveren
            </AlertDialogHeader>
            <AlertDialogBody>
              Weet je zeker dat je{' '}
              <Text as="span" fontWeight="bold">
                {vehicleToDeactivate?.license_plate}
              </Text>{' '}
              wilt deactiveren? Het voertuig wordt niet verwijderd, maar is niet meer
              beschikbaar voor nieuwe ritten.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} variant="ghost" onClick={onAlertClose}>
                Annuleren
              </Button>
              <Button colorScheme="red" onClick={handleDeactivateConfirm} ml={3}>
                Deactiveren
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};

export default ZZPVehicles;
