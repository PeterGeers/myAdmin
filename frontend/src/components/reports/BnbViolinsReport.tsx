/**
 * BNB Violins Report Component
 * 
 * Displays violin charts for BNB data distribution analysis:
 * - Price per night distribution
 * - Nights per stay distribution
 * - Statistics table with quartiles
 * - Grouping by listing or channel
 * 
 * Extracted from myAdminReports.tsx (lines 3154-3297)
 */

import React, { useState, useEffect, Suspense, useMemo } from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Grid,
  GridItem,
  Heading,
  Progress,
  Select,
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
import { buildApiUrl } from '../../config';
import { authenticatedGet } from '../../services/apiService';
import UnifiedAdminYearFilter from '../UnifiedAdminYearFilter';
import { createBnbViolinFilterAdapter } from '../UnifiedAdminYearFilterAdapters';

// Lazy load Plotly only when needed (reduces initial bundle size by ~3MB)
const Plot = React.lazy(() => import('react-plotly.js'));

interface BnbViolinFilters {
  years: string[];
  listings: string;
  channels: string;
  metric: string;
}

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

interface ViolinChartProps {
  data: ViolinDataPoint[];
  metric: string;
  groupBy: string;
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
 * Violin Chart Component using Plotly
 * Displays distribution data with kernel density estimation
 */
const ViolinChart: React.FC<ViolinChartProps> = ({ data, metric, groupBy }) => {
  const { plotData, statsData } = useMemo(() => {
    if (!data.length) return { plotData: [], statsData: [] };
    
    // Group data by the specified field (listing or channel)
    const grouped = data.reduce((acc, item) => {
      const key = item[groupBy as keyof ViolinDataPoint] as string;
      if (!acc[key]) acc[key] = [];
      acc[key].push(Number(item.value) || 0);
      return acc;
    }, {} as Record<string, number[]>);
    
    // Sort groups alphabetically
    const sortedGroups = Object.keys(grouped).sort();
    
    // Create Plotly violin traces
    const plotData = sortedGroups.map(name => ({
      type: 'violin',
      y: grouped[name],
      name: name,
      box: {
        visible: true,
        fillcolor: 'rgba(49, 130, 206, 0.5)',
        line: {
          color: 'rgb(49, 130, 206)',
          width: 2
        }
      },
      meanline: {
        visible: true,
        color: 'rgb(245, 101, 0)',
        width: 2
      },
      line: {
        color: 'rgb(49, 130, 206)',
        width: 2
      },
      fillcolor: 'rgba(49, 130, 206, 0.3)',
      opacity: 0.6,
      points: false,
      hoveron: 'violins+points',
      hovertemplate: '<b>%{fullData.name}</b><br>' +
                     'Value: %{y}<br>' +
                     '<extra></extra>'
    } as any));
    
    // Calculate statistics for the table
    const statsData: StatsData[] = sortedGroups.map(name => {
      const values = grouped[name].sort((a: number, b: number) => a - b);
      const len = values.length;
      
      const min = values[0];
      const max = values[len - 1];
      const median = len % 2 === 0 
        ? (values[len / 2 - 1] + values[len / 2]) / 2
        : values[Math.floor(len / 2)];
      const q1 = values[Math.floor(len * 0.25)];
      const q3 = values[Math.floor(len * 0.75)];
      const mean = values.reduce((sum: number, val: number) => sum + val, 0) / len;
      
      return {
        name,
        count: len,
        min,
        q1,
        median,
        mean,
        q3,
        max,
        range: max - min
      };
    });
    
    return { plotData, statsData };
  }, [data, groupBy]);
  
  if (!plotData.length) {
    return (
      <Box p={4} textAlign="center">
        <Text color="white">No data available for violin chart</Text>
      </Box>
    );
  }
  
  const metricLabel = metric === 'pricePerNight' ? 'Price per Night (€)' : 'Nights per Stay';
  const isPriceMetric = metric === 'pricePerNight';
  
  return (
    <VStack spacing={4}>
      {/* Plotly Violin Chart */}
      <Box w="100%" bg="white" borderRadius="md" p={2}>
        <Suspense fallback={
          <Box p={8} textAlign="center">
            <Progress size="xs" isIndeterminate colorScheme="orange" mb={2} />
            <Text color="gray.600" fontSize="sm">Loading violin chart...</Text>
          </Box>
        }>
          <Plot
            data={plotData as any}
            layout={{
              title: metricLabel + ' Distribution',
              yaxis: {
                title: { text: metricLabel },
                zeroline: false,
                gridcolor: '#e2e8f0'
              },
              xaxis: {
                title: { text: groupBy === 'listing' ? 'Listing' : 'Channel' },
                gridcolor: '#e2e8f0'
              },
              paper_bgcolor: 'white',
              plot_bgcolor: 'white',
              showlegend: false,
              hovermode: 'closest',
              margin: { l: 60, r: 30, t: 50, b: 100 },
              height: 500
            } as any}
            config={{
              responsive: true,
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['lasso2d', 'select2d']
            }}
            style={{ width: '100%', height: '500px' }}
          />
        </Suspense>
      </Box>
      
      {/* Statistics Summary Table */}
      <Card bg="gray.600" w="100%">
        <CardBody>
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white">{groupBy === 'listing' ? 'Listing' : 'Channel'}</Th>
                  <Th color="white" isNumeric>Count</Th>
                  <Th color="white" isNumeric>Min</Th>
                  <Th color="white" isNumeric>Q1</Th>
                  <Th color="white" isNumeric>Median</Th>
                  <Th color="white" isNumeric>Mean</Th>
                  <Th color="white" isNumeric>Q3</Th>
                  <Th color="white" isNumeric>Max</Th>
                  <Th color="white" isNumeric>Range</Th>
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
  const [bnbViolinFilters, setBnbViolinFilters] = useState<BnbViolinFilters>({
    years: [new Date().getFullYear().toString()],
    listings: 'all',
    channels: 'all',
    metric: 'pricePerNight' // 'pricePerNight' or 'nightsPerStay'
  });
  
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
    setBnbViolinLoading(true);
    try {
      const params = new URLSearchParams({
        years: bnbViolinFilters.years.join(','),
        listings: bnbViolinFilters.listings,
        channels: bnbViolinFilters.channels,
        metric: bnbViolinFilters.metric
      });
      
      const response = await authenticatedGet(buildApiUrl('/api/bnb/bnb-violin-data', params));
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
      const response = await authenticatedGet(buildApiUrl('/api/bnb/bnb-filter-options'));
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
    bnbViolinFilters.years.join(','),
    bnbViolinFilters.listings,
    bnbViolinFilters.channels,
    bnbViolinFilters.metric
  ], [bnbViolinFilters.years, bnbViolinFilters.listings, bnbViolinFilters.channels, bnbViolinFilters.metric]);
  
  useEffect(() => {
    if (bnbViolinFilters.years.length > 0) {
      fetchBnbViolinData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, bnbViolinFilterDeps);

  return (
    <VStack spacing={4} align="stretch">
      {/* Unified Year Filter for BNB Violins */}
      <UnifiedAdminYearFilter
        {...createBnbViolinFilterAdapter(
          bnbViolinFilters,
          setBnbViolinFilters,
          bnbViolinFilterOptions.years
        )}
        size="sm"
      />
      
      <Card bg="gray.700">
        <CardBody>
          <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
            <GridItem>
              <Text color="white" mb={2}>Report Type</Text>
              <Select
                value={bnbViolinFilters.metric}
                onChange={(e) => setBnbViolinFilters(prev => ({...prev, metric: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="pricePerNight">Price per Night</option>
                <option value="nightsPerStay">Days per Stay</option>
              </Select>
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>Listings</Text>
              <Select
                value={bnbViolinFilters.listings}
                onChange={(e) => setBnbViolinFilters(prev => ({...prev, listings: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="all">All Listings</option>
                {(bnbViolinFilterOptions.listings || []).map((listing, index) => (
                  <option key={`violin-listing-${listing}-${index}`} value={listing}>{listing}</option>
                ))}
              </Select>
            </GridItem>
            <GridItem>
              <Text color="white" mb={2}>Channels</Text>
              <Select
                value={bnbViolinFilters.channels}
                onChange={(e) => setBnbViolinFilters(prev => ({...prev, channels: e.target.value}))}
                bg="gray.600"
                color="white"
                size="sm"
              >
                <option value="all">All Channels</option>
                {(bnbViolinFilterOptions.channels || []).map((channel, index) => (
                  <option key={`violin-channel-${channel}-${index}`} value={channel}>{channel}</option>
                ))}
              </Select>
            </GridItem>
            <GridItem>
              <Button 
                colorScheme="orange" 
                onClick={fetchBnbViolinData} 
                isLoading={bnbViolinLoading}
                size="sm"
              >
                Generate Violin Charts
              </Button>
            </GridItem>
          </Grid>
        </CardBody>
      </Card>

      {/* Violin Charts */}
      {bnbViolinData.length > 0 && (
        <>
          {/* By Listing */}
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {bnbViolinFilters.metric === 'pricePerNight' ? 'Price per Night' : 'Days per Stay'} Distribution by Listing
              </Heading>
            </CardHeader>
            <CardBody>
              <ViolinChart 
                data={bnbViolinData} 
                metric={bnbViolinFilters.metric} 
                groupBy="listing" 
              />
            </CardBody>
          </Card>

          {/* By Channel */}
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {bnbViolinFilters.metric === 'pricePerNight' ? 'Price per Night' : 'Days per Stay'} Distribution by Channel
              </Heading>
            </CardHeader>
            <CardBody>
              <ViolinChart 
                data={bnbViolinData} 
                metric={bnbViolinFilters.metric} 
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
              <Heading size="md" color="white">BNB Violin Charts Instructions</Heading>
              <Text color="white" fontSize="sm">
                1. Select the report type: "Price per Night" or "Days per Stay"
              </Text>
              <Text color="white" fontSize="sm">
                2. Choose one or more years to include in the analysis
              </Text>
              <Text color="white" fontSize="sm">
                3. Optionally filter by specific listings or channels
              </Text>
              <Text color="white" fontSize="sm">
                4. Click "Generate Violin Charts" to view the distribution analysis
              </Text>
              <Text color="gray.400" fontSize="xs">
                Violin charts show the full distribution of values with kernel density estimation.
              </Text>
              <Text color="gray.400" fontSize="xs">
                The width of each violin represents the density of data at that value. Box plots inside show quartiles (Q1, median, Q3), and the orange line shows the mean.
              </Text>
              <Text color="gray.400" fontSize="xs">
                Interactive features: hover for details, zoom, pan, and download as image.
              </Text>
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default BnbViolinsReport;
