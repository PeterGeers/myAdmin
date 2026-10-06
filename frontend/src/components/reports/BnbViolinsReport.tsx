/**
 * BNB Violins Report Component
 * 
 * Displays violin charts for BNB data distribution analysis:
 * - Price per night distribution
 * - Nights per stay distribution
 * - Statistics table with quartiles
 * - Grouping by listing or channel
 * 
 * Extracted from myAdminReports.tsx (lines 3154-3297).
 *
 * Task 2.2 (spec `.kiro/specs/Members/member-analytics`, design C3): the bespoke
 * inline violin + stats implementation has been replaced by the shared
 * `charts/ViolinChart` (traces, Plotly rendering) and `charts/violinStats` (quartile
 * math). BNB behavior is UNCHANGED:
 *   - the chart traces + layout are produced by the shared `ViolinChart`, which lifted
 *     the BNB trace construction verbatim;
 *   - BNB keeps its OWN price-aware stats table (€ formatting for the price metric,
 *     one-decimal mean/range for the nights metric), computed via the shared
 *     `violinStats` helper, so the rendered figures and formatting are byte-identical
 *     to the previous inline table. The shared chart renders with `showStats={false}`
 *     so the generic plain-number table never double-renders here.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  Heading,
  Progress,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { FilterPanel } from '../filters/FilterPanel';
import { useTenant } from '../../context/TenantContext';
import { ViolinChart, violinStats, type ViolinDatum } from '../charts';

interface BnbViolinFilterOptions {
  years: string[];
  listings: string[];
  channels: string[];
}

interface ViolinDataPoint {
  listing: string;
  channel: string;
  value: number;
}

/** Group BNB points by the chosen domain field (listing or channel). */
type BnbGroupBy = 'listing' | 'channel';

interface BnbViolinChartProps {
  data: ViolinDataPoint[];
  metric: string;
  groupBy: BnbGroupBy;
}

interface StatsData {
  name: string;
  count: number;
  min: number;
  q1: number;
  median: number;
  mean: number;
  q3: number;
  max: number;
  range: number;
}

/**
 * BNB violin chart + stats table.
 *
 * Maps the BNB domain shape `{listing, channel, value}` onto the generic
 * `ViolinDatum {group, value}` via the selected `groupBy`, renders the shared
 * `ViolinChart` for the plot, and keeps the BNB-specific price-aware stats table
 * (computed with the shared `violinStats`).
 */
const BnbViolinChart: React.FC<BnbViolinChartProps> = ({ data, metric, groupBy }) => {
  const { t } = useTypedTranslation('reports');

  // Map {listing, channel, value} -> ViolinDatum {group, value} via the chosen
  // grouping field. This preserves the previous grouping behavior exactly: group
  // key is the listing/channel string, value is coerced to a number.
  const violinData: ViolinDatum[] = useMemo(
    () =>
      data.map((item) => ({
        group: item[groupBy],
        value: Number(item.value) || 0,
      })),
    [data, groupBy]
  );

  // BNB-specific stats table, computed with the SHARED violinStats so the quartile
  // math matches the chart. Grouping + alphabetical sort reproduce the original.
  const statsData: StatsData[] = useMemo(() => {
    if (!violinData.length) return [];

    const grouped = violinData.reduce((acc, item) => {
      const key = item.group;
      if (!acc[key]) acc[key] = [];
      acc[key].push(item.value);
      return acc;
    }, {} as Record<string, number[]>);

    return Object.keys(grouped)
      .sort()
      .map((name) => ({
        name,
        // violinStats sorts its input in place; pass a copy to be safe.
        ...violinStats([...grouped[name]]),
      }));
  }, [violinData]);

  if (!violinData.length) {
    return (
      <Box p={4} textAlign="center">
        <Text color="white">{t('charts.noData')}</Text>
      </Box>
    );
  }

  const metricLabel =
    metric === 'pricePerNight' ? t('bnb.pricePerNightEuro') : t('bnb.nightsPerStay');
  const groupLabel = groupBy === 'listing' ? t('filters.listing') : t('filters.channel');
  const isPriceMetric = metric === 'pricePerNight';

  return (
    <VStack spacing={4}>
      {/* Shared Plotly Violin Chart — stats table rendered separately below to keep
          the BNB-specific price/decimal formatting. */}
      <ViolinChart
        data={violinData}
        metricLabel={metricLabel}
        groupLabel={groupLabel}
        showStats={false}
      />

      {/* BNB price-aware Statistics Summary Table (unchanged rendering) */}
      <Card bg="gray.600" w="100%">
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white">{groupLabel}</Th>
                  <Th color="white" isNumeric>{t('charts.count')}</Th>
                  <Th color="white" isNumeric>{t('bnb.min')}</Th>
                  <Th color="white" isNumeric>{t('bnb.q1')}</Th>
                  <Th color="white" isNumeric>{t('charts.median')}</Th>
                  <Th color="white" isNumeric>{t('charts.average')}</Th>
                  <Th color="white" isNumeric>{t('bnb.q3')}</Th>
                  <Th color="white" isNumeric>{t('bnb.max')}</Th>
                  <Th color="white" isNumeric>{t('bnb.range')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {statsData.map((item, index) => (
                  <Tr key={index}>
                    <Td color="white" fontSize="sm">{item.name}</Td>
                    <Td color="white" fontSize="sm" isNumeric>{item.count}</Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.min.toFixed(2)}` : item.min}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.q1.toFixed(2)}` : item.q1}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.median.toFixed(2)}` : item.median}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.mean.toFixed(2)}` : item.mean.toFixed(1)}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.q3.toFixed(2)}` : item.q3}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.max.toFixed(2)}` : item.max}
                    </Td>
                    <Td color="white" fontSize="sm" isNumeric>
                      {isPriceMetric ? `€${item.range.toFixed(2)}` : item.range.toFixed(1)}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>
    </VStack>
  );
};

/**
 * Main BNB Violins Report Component
 */
const BnbViolinsReport: React.FC = () => {
  const { t } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();

  // Metric options constant
  const metricOptions = [
    { value: 'pricePerNight', label: t('bnb.pricePerNight') },
    { value: 'nightsPerStay', label: t('bnb.daysPerStay') }
  ];

  // Separate state for each filter
  const [selectedYears, setSelectedYears] = useState<string[]>([new Date().getFullYear().toString()]);
  const [selectedMetric, setSelectedMetric] = useState<string>('pricePerNight'); // 'pricePerNight' or 'nightsPerStay'
  const [selectedListings, setSelectedListings] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);

  const [bnbViolinFilterOptions, setBnbViolinFilterOptions] = useState<BnbViolinFilterOptions>({
    years: [],
    listings: [],
    channels: []
  });

  const [bnbViolinData, setBnbViolinData] = useState<ViolinDataPoint[]>([]);
  const [bnbViolinLoading, setBnbViolinLoading] = useState(false);

  /**
   * Fetch BNB violin data from API
   */
  const fetchBnbViolinData = async () => {
    if (!currentTenant) {
      console.error('No tenant selected for BNB violin data');
      return;
    }

    setBnbViolinLoading(true);
    try {
      const params = new URLSearchParams({
        years: selectedYears.join(','),
        listings: selectedListings.length > 0 ? selectedListings.join(',') : 'all',
        channels: selectedChannels.length > 0 ? selectedChannels.join(',') : 'all',
        metric: selectedMetric,
        administration: currentTenant
      });

      const response = await authenticatedGet(buildEndpoint('/api/bnb/bnb-violin-data', params));
      const data = await response.json();

      if (data.success) {
        setBnbViolinData(data.data);
      }
    } catch (err) {
      console.error('Error fetching BNB violin data:', err);
    } finally {
      setBnbViolinLoading(false);
    }
  };

  /**
   * Fetch filter options (years, listings, channels)
   */
  const fetchBnbViolinFilterOptions = async () => {
    try {
      const response = await authenticatedGet(buildEndpoint('/api/bnb/bnb-filter-options'));
      const data = await response.json();
      if (data.success) {
        setBnbViolinFilterOptions({
          years: data.years || [],
          listings: data.listings || [],
          channels: data.channels || []
        });
      }
    } catch (err) {
      console.error('Error fetching BNB violin filter options:', err);
    }
  };

  // Initialize filter options on mount
  useEffect(() => {
    fetchBnbViolinFilterOptions();
  }, []);

  // Refetch data when filters change
  const bnbViolinFilterDeps = useMemo(() => [
    selectedYears.join(','),
    selectedListings.join(','),
    selectedChannels.join(','),
    selectedMetric,
    currentTenant
  ], [selectedYears, selectedListings, selectedChannels, selectedMetric, currentTenant]);

  useEffect(() => {
    if (selectedYears.length > 0 && currentTenant) {
      fetchBnbViolinData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, bnbViolinFilterDeps);

  return (
    <VStack spacing={4} align="stretch">
      {/* Tenant validation alert */}
      {!currentTenant && (
        <Card bg="orange.500">
          <CardBody>
            <Text color="white" fontWeight="bold">
              {t('messages.noTenantSelected')}
            </Text>
          </CardBody>
        </Card>
      )}

      {/* Filter Panel */}
      <Card bg="gray.700">
        <CardBody>
          <FilterPanel
            layout="grid"
            gridColumns={4}
            size="sm"
            spacing={4}
            filters={[
              {
                type: 'multi',
                label: t('filters.year'),
                options: bnbViolinFilterOptions.years,
                value: selectedYears,
                onChange: setSelectedYears,
                placeholder: t('filters.selectYear')
              },
              {
                type: 'single',
                label: t('filters.reportType'),
                options: metricOptions,
                value: metricOptions.find(opt => opt.value === selectedMetric) || metricOptions[0],
                onChange: (opt: { value: string; label: string }) => setSelectedMetric(opt.value),
                getOptionLabel: (opt) => opt.label,
                getOptionValue: (opt) => opt.value
              },
              {
                type: 'multi',
                label: t('filters.listings'),
                options: bnbViolinFilterOptions.listings,
                value: selectedListings,
                onChange: setSelectedListings,
                placeholder: t('filters.allListings'),
                treatEmptyAsSelected: true
              },
              {
                type: 'multi',
                label: t('filters.channels'),
                options: bnbViolinFilterOptions.channels,
                value: selectedChannels,
                onChange: setSelectedChannels,
                placeholder: t('filters.allChannels'),
                treatEmptyAsSelected: true
              }
            ]}
          />
          {bnbViolinLoading && (
            <Box mt={4}>
              <Progress size="xs" isIndeterminate colorScheme="orange" />
              <Text color="white" fontSize="sm" mt={2}>{t('bnb.loadingViolinChartData')}</Text>
            </Box>
          )}
        </CardBody>
      </Card>

      {/* Violin Charts */}
      {bnbViolinData.length > 0 && (
        <>
          {/* By Listing */}
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {selectedMetric === 'pricePerNight' ? t('bnb.pricePerNight') : t('bnb.daysPerStay')} {t('bnb.distributionByListing')}
              </Heading>
            </CardHeader>
            <CardBody>
              <BnbViolinChart
                data={bnbViolinData}
                metric={selectedMetric}
                groupBy="listing"
              />
            </CardBody>
          </Card>

          {/* By Channel */}
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {selectedMetric === 'pricePerNight' ? t('bnb.pricePerNight') : t('bnb.daysPerStay')} {t('bnb.distributionByChannel')}
              </Heading>
            </CardHeader>
            <CardBody>
              <BnbViolinChart
                data={bnbViolinData}
                metric={selectedMetric}
                groupBy="channel"
              />
            </CardBody>
          </Card>
        </>
      )}

      {/* Instructions */}
      {bnbViolinData.length === 0 && !bnbViolinLoading && (
        <Card bg="gray.700">
          <CardBody>
            <VStack spacing={3} align="start">
              <Heading size="md" color="white">{t('titles.bnbViolins')} {t('common:labels.instructions')}</Heading>
              <Text color="white" fontSize="sm">
                1. {t('bnb.selectReportType')}
              </Text>
              <Text color="white" fontSize="sm">
                2. {t('bnb.chooseYearsForAnalysis')}
              </Text>
              <Text color="white" fontSize="sm">
                3. {t('bnb.optionallyFilterByListingsOrChannels')}
              </Text>
              <Text color="white" fontSize="sm">
                4. {t('bnb.chartsAutoUpdate')}
              </Text>
              <Text color="gray.400" fontSize="xs">
                {t('bnb.violinChartsShowDistribution')}
              </Text>
              <Text color="gray.400" fontSize="xs">
                {t('bnb.violinWidthExplanation')}
              </Text>
              <Text color="gray.400" fontSize="xs">
                {t('bnb.interactiveFeatures')}
              </Text>
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default BnbViolinsReport;
