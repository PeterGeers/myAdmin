/**
 * ZZP Trips (Rittenregistratie) page — tabbed layout with Ritten, Voertuigen, Importeren.
 * Vehicle-scoped mileage tracking for Dutch tax compliance.
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useFilterableTable + FilterableHeader for inline column text filters + sort
 * - Dropdown filters (vehicle, year, category) above the table for server-side filtering
 *
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.2
 */

import React, { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Select, HStack,
  Table, Thead, Tbody, Tr, Td, Badge,
  Menu, MenuButton, MenuList, MenuItem, useDisclosure,
  Tabs, TabList, Tab, TabPanels, TabPanel,
} from '@chakra-ui/react';
import { AddIcon, ChevronDownIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { getTrips, getTripSummary, exportTrips } from '../services/tripService';
import { getVehicles } from '../services/vehicleService';
import type { Trip, TripFilters, TripSummary, Vehicle } from '../types/zzpTrips';
import { TripModal } from '../components/zzp/TripModal';
import { BijtellingWidget } from '../components/zzp/BijtellingWidget';
import { GapFillBanner } from '../components/zzp/GapFillBanner';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';

const ZZPVehicles = lazy(() => import('./ZZPVehicles'));
const ZZPTripImport = lazy(() => import('./ZZPTripImport'));

/** Server-side page size for the trips table. */
const PAGE_SIZE = 50;

/* ─── Helpers ─── */

/** Format date to Dutch locale (dd-mm-yyyy). */
function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleDateString('nl-NL', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/* ─── Summary Bar ─── */
interface SummaryBarProps {
  summary: TripSummary | null;
  t: (key: string) => string;
}

const SummaryBar: React.FC<SummaryBarProps> = ({ summary, t }) => (
  <Flex gap={4} mb={4} wrap="wrap" bg="gray.700" p={3} borderRadius="md">
    <Box>
      <Text fontSize="xs" color="gray.400">{t('trips.summary.totalKm')}</Text>
      <Text fontWeight="bold" color="white">{summary?.total_km ?? 0} km</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="gray.400">{t('trips.categories.zakelijk')}</Text>
      <Text fontWeight="bold" color="white">{summary?.zakelijk_km ?? 0} km</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="gray.400">{t('trips.categories.prive')}</Text>
      <Text fontWeight="bold" color="white">{summary?.prive_km ?? 0} km</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="gray.400">{t('trips.categories.woonWerk')}</Text>
      <Text fontWeight="bold" color="white">{summary?.woonwerk_km ?? 0} km</Text>
    </Box>
  </Flex>
);

/* ─── Main Page ─── */
const ZZPTrips: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen: _isOpen, onOpen, onClose: _onClose } = useDisclosure();

  // Data state
  const [trips, setTrips] = useState<Trip[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<number | null>(null);
  const [summary, setSummary] = useState<TripSummary | null>(null);
  const [selectedTrip, setSelectedTrip] = useState<Trip | null>(null);
  const [loading, setLoading] = useState(true);

  // Server-side pagination state
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);

  // Server-side filter state (vehicle, year, category — triggers API reload)
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [category, setCategory] = useState('');

  // Gap-fill state (set from createTrip response)
  const [gapFillOffer, setGapFillOffer] = useState<{
    start_odometer: number;
    end_odometer: number;
    suggested_category: string;
    suggested_purpose: string;
  } | null>(null);
  const [gapWarning, setGapWarning] = useState<{
    gap_km: number;
    previous_end_odometer: number;
    current_start_odometer: number;
    message: string;
  } | null>(null);

  // Client-side column filtering + sorting via table-filter-framework-v2
  const tripRows = useMemo(() => {
    // Sort trips by date + start_odometer to detect chain breaks
    const sorted = [...trips].sort((a, b) => {
      const dateCompare = a.trip_date.localeCompare(b.trip_date);
      return dateCompare !== 0 ? dateCompare : a.start_odometer - b.start_odometer;
    });

    return sorted.map((trip, idx) => {
      // Check odometer chain: does this trip's start match previous trip's end?
      let gapFlag = '';
      if (idx > 0) {
        const prevEnd = sorted[idx - 1].end_odometer;
        if (trip.start_odometer !== prevEnd) {
          const diff = trip.start_odometer - prevEnd;
          gapFlag = `${diff > 0 ? '+' : ''}${diff} km`;
        }
      }

      return {
        ...trip,
        formatted_date: formatDate(trip.trip_date),
        client_label: trip.client_name || '',
        gap_flag: gapFlag,
      };
    });
  }, [trips]);

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable(tripRows, {
    initialFilters: {
      trip_date: '',
      start_address: '',
      end_address: '',
      end_odometer: '',
      distance_km: '',
      trip_category: '',
      trip_purpose: '',
      client_label: '',
      gap_flag: '',
    },
    defaultSort: { field: 'trip_date', direction: 'desc' },
  });

  // Build server-side filters
  const buildFilters = useCallback((): TripFilters => {
    const filters: TripFilters = {};
    if (selectedVehicle) filters.vehicle_id = selectedVehicle;
    if (category) filters.trip_category = category;
    filters.limit = PAGE_SIZE;
    filters.offset = page * PAGE_SIZE;
    return filters;
  }, [selectedVehicle, category, page]);

  // Load vehicles on mount
  useEffect(() => {
    const loadVehicles = async () => {
      try {
        const resp = await getVehicles(true);
        if (resp.success && resp.data.length > 0) {
          setVehicles(resp.data);
          setSelectedVehicle(resp.data[0].id);
        }
      } catch {
        toast({ title: 'Error loading vehicles', status: 'error', duration: 3000 });
      }
    };
    loadVehicles();
  }, [toast]);

  // Load trips when vehicle or filters change
  const loadTrips = useCallback(async () => {
    if (!selectedVehicle) {
      setTrips([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const filters = buildFilters();
      const resp = await getTrips(filters);
      if (resp.success) {
        setTrips(resp.data || []);
        setTotal(resp.total ?? 0);
      }
    } catch {
      toast({ title: 'Error loading trips', status: 'error', duration: 3000 });
    } finally {
      setLoading(false);
    }
  }, [selectedVehicle, buildFilters, toast]);

  useEffect(() => { loadTrips(); }, [loadTrips]);

  // Reset to the first page whenever the server-side filters change, so a
  // narrower result set never leaves the user stranded on an empty page.
  useEffect(() => { setPage(0); }, [selectedVehicle, category, year]);

  // Load summary when vehicle or year changes
  const loadSummary = useCallback(async () => {
    if (!selectedVehicle) {
      setSummary(null);
      return;
    }
    try {
      const resp = await getTripSummary(selectedVehicle, year);
      if (resp.success) {
        setSummary(resp.data);
      }
    } catch {
      // Non-critical, summary just won't show
    }
  }, [selectedVehicle, year]);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  // Export handler
  const handleExport = async (format: string) => {
    if (!selectedVehicle) return;
    try {
      toast({ title: t('trips.export.generating'), status: 'info', duration: 2000 });
      const blob = await exportTrips(selectedVehicle, year, format);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `ritten_${year}.${format === 'xlsx' ? 'xlsx' : format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast({ title: t('trips.export.downloadReady'), status: 'success', duration: 2000 });
    } catch (err) {
      toast({
        title: err instanceof Error ? err.message : 'Export failed',
        status: 'error',
        duration: 3000,
      });
    }
  };

  // Row click handler
  const handleRowClick = (trip: Trip) => {
    setSelectedTrip(trip);
    onOpen();
  };

  // New trip handler
  const handleNewTrip = () => {
    setSelectedTrip(null);
    onOpen();
  };

  // Year options for selector
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i);

  return (
    <Box p={4} bg="gray.800" color="white" minH="100vh">
      <Tabs variant="enclosed" colorScheme="orange">
        <TabList mb={4}>
          <Tab>Ritten</Tab>
          <Tab>Voertuigen</Tab>
          <Tab>Importeren</Tab>
        </TabList>

        <TabPanels>
          {/* Tab 1: Ritten (main trip table) */}
          <TabPanel p={0}>
            {/* Header */}
            <Flex justify="space-between" align="center" mb={4} wrap="wrap" gap={2}>
              <Text fontSize="xl" fontWeight="bold">{t('trips.title')}</Text>
              <HStack spacing={2}>
                <Button
                  colorScheme="orange"
                  size="sm"
                  leftIcon={<AddIcon />}
                  onClick={handleNewTrip}
                >
                  {t('trips.newTrip')}
                </Button>
                <Menu>
                  <MenuButton as={Button} size="sm" rightIcon={<ChevronDownIcon />}>
                    {t('trips.export.title')}
                  </MenuButton>
                  <MenuList bg="gray.700" borderColor="gray.600">
                    <MenuItem bg="gray.700" _hover={{ bg: 'gray.600' }} onClick={() => handleExport('pdf')}>
                      {t('trips.export.pdf')}
                    </MenuItem>
                    <MenuItem bg="gray.700" _hover={{ bg: 'gray.600' }} onClick={() => handleExport('csv')}>
                      {t('trips.export.csv')}
                    </MenuItem>
                    <MenuItem bg="gray.700" _hover={{ bg: 'gray.600' }} onClick={() => handleExport('xlsx')}>
                      {t('trips.export.excel')}
                    </MenuItem>
                  </MenuList>
                </Menu>
              </HStack>
            </Flex>

            {/* Vehicle Selector + Year */}
            <Flex gap={3} mb={4} wrap="wrap">
              <Select
                size="sm"
                w={{ base: '100%', md: '250px' }}
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                value={selectedVehicle ?? ''}
                onChange={(e) => setSelectedVehicle(Number(e.target.value) || null)}
                placeholder={t('trips.filters.allVehicles')}
              >
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.license_plate} — {v.make} {v.model}
                  </option>
                ))}
              </Select>
              <Select
                size="sm"
                w={{ base: '50%', md: '120px' }}
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </Select>
            </Flex>

            {/* Summary Bar */}
            <SummaryBar summary={summary} t={t} />

            {/* Bijtelling Widget (only shows for business vehicles) */}
            <BijtellingWidget
              summary={summary}
              vehicleType={vehicles.find((v) => v.id === selectedVehicle)?.vehicle_type}
            />

            {/* Filter Panel — dropdown filters above table (server-side) */}
            <Flex gap={3} mb={4} wrap="wrap" align="center">
              <Select
                size="sm"
                w={{ base: '100%', md: '160px' }}
                bg="gray.700"
                color="white"
                borderColor="gray.600"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder={t('trips.filters.allCategories')}
              >
                <option value="Zakelijk">{t('trips.categories.zakelijk')}</option>
                <option value="Privé">{t('trips.categories.prive')}</option>
                <option value="Woon-werk">{t('trips.categories.woonWerk')}</option>
              </Select>
            </Flex>

            {/* Gap-Fill Banner */}
            {selectedVehicle && (
              <GapFillBanner
                gapFillOffer={gapFillOffer}
                gapWarning={gapWarning}
                vehicleId={selectedVehicle}
                onAccepted={() => {
                  setGapFillOffer(null);
                  setGapWarning(null);
                  loadTrips();
                }}
              />
            )}

            {/* Content */}
            {loading ? (
              <Flex justify="center" py={10}>
                <Spinner color="orange.300" size="lg" />
              </Flex>
            ) : trips.length === 0 ? (
              <Box textAlign="center" py={10}>
                <Text color="gray.400">{t('trips.noTrips')}</Text>
              </Box>
            ) : (
              <Box overflowX="auto">
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      <FilterableHeader
                        label={t('trips.labels.date')}
                        filterValue={filters.trip_date}
                        onFilterChange={(v) => setFilter('trip_date', v)}
                        sortable
                        sortDirection={sortField === 'trip_date' ? sortDirection : null}
                        onSort={() => handleSort('trip_date')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label={t('trips.labels.startAddress')}
                        filterValue={filters.start_address}
                        onFilterChange={(v) => setFilter('start_address', v)}
                        sortable
                        sortDirection={sortField === 'start_address' ? sortDirection : null}
                        onSort={() => handleSort('start_address')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label={t('trips.labels.endAddress')}
                        filterValue={filters.end_address}
                        onFilterChange={(v) => setFilter('end_address', v)}
                        sortable
                        sortDirection={sortField === 'end_address' ? sortDirection : null}
                        onSort={() => handleSort('end_address')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label={t('trips.labels.endOdometer')}
                        filterValue={filters.end_odometer}
                        onFilterChange={(v) => setFilter('end_odometer', v)}
                        sortable
                        sortDirection={sortField === 'end_odometer' ? sortDirection : null}
                        onSort={() => handleSort('end_odometer')}
                        isNumeric
                        placeholder="km"
                      />
                      <FilterableHeader
                        label={t('trips.labels.distance')}
                        filterValue={filters.distance_km}
                        onFilterChange={(v) => setFilter('distance_km', v)}
                        sortable
                        sortDirection={sortField === 'distance_km' ? sortDirection : null}
                        onSort={() => handleSort('distance_km')}
                        isNumeric
                        placeholder="km"
                      />
                      <FilterableHeader
                        label={t('trips.labels.category')}
                        filterValue={filters.trip_category}
                        onFilterChange={(v) => setFilter('trip_category', v)}
                        sortable
                        sortDirection={sortField === 'trip_category' ? sortDirection : null}
                        onSort={() => handleSort('trip_category')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label={t('trips.labels.purpose')}
                        filterValue={filters.trip_purpose}
                        onFilterChange={(v) => setFilter('trip_purpose', v)}
                        sortable
                        sortDirection={sortField === 'trip_purpose' ? sortDirection : null}
                        onSort={() => handleSort('trip_purpose')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label={t('trips.labels.client')}
                        filterValue={filters.client_label}
                        onFilterChange={(v) => setFilter('client_label', v)}
                        sortable
                        sortDirection={sortField === 'client_label' ? sortDirection : null}
                        onSort={() => handleSort('client_label')}
                        placeholder="Filter..."
                      />
                      <FilterableHeader
                        label="Gap"
                        filterValue={filters.gap_flag}
                        onFilterChange={(v) => setFilter('gap_flag', v)}
                        placeholder="+ / -"
                      />
                    </Tr>
                  </Thead>
                  <Tbody>
                    {processedData.map((trip) => (
                      <Tr
                        key={trip.id}
                        cursor="pointer"
                        _hover={{ bg: 'gray.700' }}
                        onClick={() => handleRowClick(trip)}
                      >
                        <Td maxW="50px">{formatDate(trip.trip_date)}</Td>
                        <Td maxW="180px" isTruncated title={trip.start_address}>{trip.start_address}</Td>
                        <Td maxW="180px" isTruncated title={trip.end_address}>{trip.end_address}</Td>
                        <Td isNumeric maxW="80px">{trip.end_odometer}</Td>
                        <Td isNumeric maxW="60px">{trip.distance_km}</Td>
                        <Td maxW="90px">
                          <Badge
                            colorScheme={
                              trip.trip_category === 'Zakelijk' ? 'blue'
                                : trip.trip_category === 'Privé' ? 'purple'
                                  : 'orange'
                            }
                            variant="subtle"
                          >
                            {trip.trip_category}
                          </Badge>
                        </Td>
                        <Td maxW="130px" isTruncated title={trip.trip_purpose}>{trip.trip_purpose || '-'}</Td>
                        <Td maxW="140px" isTruncated title={trip.client_name ?? ''}>{trip.client_name ?? ''}</Td>
                        <Td>
                          {trip.gap_flag ? (
                            <Badge colorScheme="red" variant="subtle" fontSize="xs">
                              {trip.gap_flag}
                            </Badge>
                          ) : null}
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </Box>
            )}

            {/* Pagination controls (server-side next/prev) */}
            {!loading && total > 0 && (
              <Flex justify="space-between" align="center" mt={4} wrap="wrap" gap={2}>
                <Text fontSize="sm" color="gray.400">
                  {total === 0
                    ? '0'
                    : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)}`} / {total}
                </Text>
                <HStack spacing={2}>
                  <Button
                    size="sm"
                    variant="outline"
                    colorScheme="orange"
                    color="orange.200"
                    borderColor="orange.400"
                    _hover={{ bg: 'orange.600', color: 'white' }}
                    _disabled={{ opacity: 0.4, cursor: 'not-allowed', color: 'gray.500', borderColor: 'gray.600' }}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    isDisabled={page === 0}
                  >
                    {t('common.previous')}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    colorScheme="orange"
                    color="orange.200"
                    borderColor="orange.400"
                    _hover={{ bg: 'orange.600', color: 'white' }}
                    _disabled={{ opacity: 0.4, cursor: 'not-allowed', color: 'gray.500', borderColor: 'gray.600' }}
                    onClick={() => setPage((p) => p + 1)}
                    isDisabled={(page + 1) * PAGE_SIZE >= total}
                  >
                    {t('common.next')}
                  </Button>
                </HStack>
              </Flex>
            )}

            {/* TripModal for create/edit */}
            {selectedVehicle && (
              <TripModal
                isOpen={_isOpen}
                onClose={_onClose}
                trip={selectedTrip}
                onSaved={() => { loadTrips(); loadSummary(); }}
                vehicleId={selectedVehicle}
              />
            )}
          </TabPanel>

          {/* Tab 2: Voertuigen */}
          <TabPanel p={0}>
            <Suspense fallback={<Flex justify="center" py={10}><Spinner color="orange.300" size="lg" /></Flex>}>
              <ZZPVehicles />
            </Suspense>
          </TabPanel>

          {/* Tab 3: Importeren */}
          <TabPanel p={0}>
            <Suspense fallback={<Flex justify="center" py={10}><Spinner color="orange.300" size="lg" /></Flex>}>
              <ZZPTripImport />
            </Suspense>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default ZZPTrips;
