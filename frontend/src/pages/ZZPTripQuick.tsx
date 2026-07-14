import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Flex,
  Button,
  Text,
  Select,
  VStack,
  HStack,
  FormControl,
  FormLabel,
  Input,
  useToast,
  Spinner,
  Badge,
} from '@chakra-ui/react';
import { createTrip, getTrips } from '../services/tripService';
import { getVehicles } from '../services/vehicleService';
import { getRoutePresets } from '../services/routePresetService';
import type { Vehicle, Trip, RoutePreset } from '../types/zzpTrips';
import { RoutePresetCards } from '../components/zzp/RoutePresetCards';

/**
 * Mobile-optimized quick trip entry page.
 * Standalone layout — no sidebar, minimal chrome.
 * Designed for fast one-handed trip registration.
 */
const ZZPTripQuick: React.FC = () => {
  const toast = useToast();
  const endOdometerRef = useRef<HTMLInputElement>(null);

  // Data state
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [presets, setPresets] = useState<RoutePreset[]>([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState<number | null>(null);
  const [lastTrip, setLastTrip] = useState<Trip | null>(null);

  // Form state
  const [startOdometer, setStartOdometer] = useState<string>('');
  const [endOdometer, setEndOdometer] = useState<string>('');
  const [startAddress, setStartAddress] = useState<string>('');
  const [endAddress, setEndAddress] = useState<string>('');
  const [tripCategory, setTripCategory] = useState<string>('Zakelijk');
  const [tripPurpose, setTripPurpose] = useState<string>('');
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);

  // Timer state
  const [timerMode, setTimerMode] = useState(false);
  const [startTime, setStartTime] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // UI state
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      try {
        const [vehicleResp, presetResp] = await Promise.all([
          getVehicles(true),
          getRoutePresets(),
        ]);

        const activeVehicles = vehicleResp.data || [];
        setVehicles(activeVehicles);
        setPresets(presetResp.data || []);

        // Auto-select first active vehicle
        if (activeVehicles.length > 0) {
          setSelectedVehicleId(activeVehicles[0].id);
        }
      } catch (err) {
        toast({
          title: 'Fout bij laden',
          description: 'Kan gegevens niet ophalen.',
          status: 'error',
          duration: 4000,
        });
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [toast]);

  // Fetch last trip when vehicle changes to pre-fill start odometer
  useEffect(() => {
    if (!selectedVehicleId) return;

    const fetchLastTrip = async () => {
      try {
        const resp = await getTrips({ vehicle_id: selectedVehicleId, limit: 1 });
        const trips = resp.data || [];
        if (trips.length > 0) {
          const last = trips[0];
          setLastTrip(last);
          setStartOdometer(String(last.end_odometer));
        } else {
          // No previous trips — use vehicle start_odometer
          const vehicle = vehicles.find((v) => v.id === selectedVehicleId);
          if (vehicle) {
            setStartOdometer(String(vehicle.start_odometer));
          }
          setLastTrip(null);
        }
      } catch {
        // Silently fail — user can enter manually
      }
    };

    fetchLastTrip();
  }, [selectedVehicleId, vehicles]);

  // Timer interval
  useEffect(() => {
    if (timerMode) {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [timerMode]);

  const formatElapsed = (seconds: number): string => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const handlePresetSelect = useCallback((preset: RoutePreset) => {
    setSelectedPresetId(preset.id);
    setStartAddress(preset.from_address);
    setEndAddress(preset.to_address);
    if (preset.default_category) setTripCategory(preset.default_category);
    if (preset.default_purpose) setTripPurpose(preset.default_purpose);
  }, []);

  const handleStartTrip = () => {
    const now = new Date().toLocaleTimeString('nl-NL', {
      hour: '2-digit',
      minute: '2-digit',
    });
    setStartTime(now);
    setTimerMode(true);
    setElapsedSeconds(0);
  };

  const handleStopTrip = () => {
    setTimerMode(false);
    // Focus on end odometer input for quick entry
    setTimeout(() => endOdometerRef.current?.focus(), 100);
  };

  const handleSubmit = async () => {
    // Validation
    if (!selectedVehicleId) {
      toast({ title: 'Selecteer een voertuig', status: 'warning', duration: 3000 });
      return;
    }
    if (!startAddress || !endAddress) {
      toast({ title: 'Selecteer een route of vul adressen in', status: 'warning', duration: 3000 });
      return;
    }
    const startKm = Number(startOdometer);
    const endKm = Number(endOdometer);
    if (!endOdometer || isNaN(endKm) || endKm <= startKm) {
      toast({ title: 'Vul een geldige eind km-stand in', status: 'warning', duration: 3000 });
      return;
    }

    setSubmitting(true);
    try {
      const tripData: Partial<Trip> = {
        vehicle_id: selectedVehicleId,
        trip_date: new Date().toISOString().split('T')[0],
        start_address: startAddress,
        end_address: endAddress,
        start_odometer: startKm,
        end_odometer: endKm,
        distance_km: endKm - startKm,
        trip_category: tripCategory,
        trip_purpose: tripPurpose || `${startAddress} → ${endAddress}`,
        start_time: startTime || null,
        end_time: timerMode
          ? null
          : new Date().toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' }),
      };

      await createTrip(tripData);

      toast({
        title: 'Rit geregistreerd!',
        description: `${startAddress} → ${endAddress} (${endKm - startKm} km)`,
        status: 'success',
        duration: 4000,
      });

      // Reset form for next trip
      setStartOdometer(String(endKm));
      setEndOdometer('');
      setStartAddress('');
      setEndAddress('');
      setTripPurpose('');
      setSelectedPresetId(null);
      setStartTime(null);
      setTimerMode(false);
      setElapsedSeconds(0);
    } catch (err) {
      toast({
        title: 'Fout bij registreren',
        description: 'Probeer opnieuw.',
        status: 'error',
        duration: 4000,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const goBack = () => {
    // Navigate back — in this SPA, we rely on window.history
    window.history.back();
  };

  if (loading) {
    return (
      <Box p={4} bg="gray.800" color="white" minH="100vh" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Spinner size="lg" color="orange.400" />
          <Text color="gray.400">Laden...</Text>
        </VStack>
      </Box>
    );
  }

  return (
    <Box p={4} bg="gray.800" color="white" minH="100vh" maxW="500px" mx="auto">
      {/* Header - minimal */}
      <Flex align="center" mb={4}>
        <Button
          variant="ghost"
          color="gray.300"
          onClick={goBack}
          minH="44px"
          _hover={{ bg: 'gray.700' }}
        >
          ← Terug
        </Button>
        <Text fontSize="lg" fontWeight="bold" ml={2} color="orange.400">
          Rittenregistratie
        </Text>
      </Flex>

      {/* Vehicle selector (compact) */}
      <Select
        mb={4}
        bg="gray.700"
        borderColor="gray.600"
        color="white"
        value={selectedVehicleId ?? ''}
        onChange={(e) => setSelectedVehicleId(Number(e.target.value))}
        minH="44px"
        aria-label="Selecteer voertuig"
      >
        {vehicles.map((v) => (
          <option key={v.id} value={v.id} style={{ background: '#2D3748' }}>
            {v.license_plate} {v.make ? `— ${v.make} ${v.model || ''}` : ''}
          </option>
        ))}
      </Select>

      {/* Route Preset Cards */}
      <Text fontSize="sm" color="gray.400" mb={2}>
        Snelkeuze route
      </Text>
      <RoutePresetCards
        presets={presets}
        onSelect={handlePresetSelect}
        selectedId={selectedPresetId}
      />

      {/* Form fields */}
      <VStack spacing={3} mt={4} align="stretch">
        {/* Addresses (shown when preset selected or manual entry) */}
        <FormControl>
          <FormLabel fontSize="sm" color="gray.400">
            Route
          </FormLabel>
          <HStack>
            <Input
              value={startAddress}
              onChange={(e) => setStartAddress(e.target.value)}
              placeholder="Van"
              bg="gray.700"
              borderColor="gray.600"
              size="sm"
              minH="44px"
            />
            <Input
              value={endAddress}
              onChange={(e) => setEndAddress(e.target.value)}
              placeholder="Naar"
              bg="gray.700"
              borderColor="gray.600"
              size="sm"
              minH="44px"
            />
          </HStack>
        </FormControl>

        {/* Odometer */}
        <FormControl>
          <FormLabel fontSize="sm" color="gray.400">
            Km-stand
          </FormLabel>
          <HStack>
            <Input
              value={startOdometer}
              isReadOnly
              bg="gray.900"
              borderColor="gray.600"
              color="gray.400"
              size="sm"
              minH="44px"
              aria-label="Start km-stand"
            />
            <Input
              ref={endOdometerRef}
              value={endOdometer}
              onChange={(e) => setEndOdometer(e.target.value)}
              placeholder="Eind"
              bg="gray.700"
              borderColor="gray.600"
              type="number"
              size="sm"
              minH="44px"
              aria-label="Eind km-stand"
            />
          </HStack>
          {lastTrip && (
            <Text fontSize="xs" color="gray.500" mt={1}>
              Vorige: {lastTrip.end_odometer} km ({lastTrip.end_address})
            </Text>
          )}
        </FormControl>

        {/* Category */}
        <FormControl>
          <FormLabel fontSize="sm" color="gray.400">
            Categorie
          </FormLabel>
          <Select
            value={tripCategory}
            onChange={(e) => setTripCategory(e.target.value)}
            bg="gray.700"
            borderColor="gray.600"
            size="sm"
            minH="44px"
          >
            <option value="Zakelijk" style={{ background: '#2D3748' }}>Zakelijk</option>
            <option value="Woon-werk" style={{ background: '#2D3748' }}>Woon-werk</option>
            <option value="Privé" style={{ background: '#2D3748' }}>Privé</option>
          </Select>
        </FormControl>

        {/* Start/Stop timer */}
        <Box>
          {!timerMode ? (
            <Button
              w="full"
              size="md"
              variant="outline"
              colorScheme="green"
              onClick={handleStartTrip}
              minH="44px"
              leftIcon={<Text>▶</Text>}
            >
              Start Rit
            </Button>
          ) : (
            <VStack spacing={2}>
              <Flex
                w="full"
                align="center"
                justify="space-between"
                bg="gray.900"
                p={3}
                borderRadius="md"
              >
                <HStack>
                  <Badge colorScheme="green" variant="subtle" fontSize="xs">
                    ACTIEF
                  </Badge>
                  <Text fontSize="sm" color="gray.400">
                    Start: {startTime}
                  </Text>
                </HStack>
                <Text fontSize="lg" fontWeight="mono" color="green.300">
                  {formatElapsed(elapsedSeconds)}
                </Text>
              </Flex>
              <Button
                w="full"
                size="md"
                colorScheme="red"
                variant="outline"
                onClick={handleStopTrip}
                minH="44px"
                leftIcon={<Text>⏹</Text>}
              >
                Stop Rit
              </Button>
            </VStack>
          )}
        </Box>
      </VStack>

      {/* Primary action */}
      <Button
        w="full"
        size="lg"
        colorScheme="orange"
        mt={6}
        onClick={handleSubmit}
        isLoading={submitting}
        loadingText="Registreren..."
        minH="56px"
        fontSize="lg"
        fontWeight="bold"
        isDisabled={!endOdometer || !startAddress || !endAddress}
      >
        REGISTREER RIT
      </Button>

      {/* Distance preview */}
      {endOdometer && startOdometer && Number(endOdometer) > Number(startOdometer) && (
        <Text textAlign="center" mt={2} fontSize="sm" color="gray.400">
          Afstand: {Number(endOdometer) - Number(startOdometer)} km
        </Text>
      )}
    </Box>
  );
};

export default ZZPTripQuick;
