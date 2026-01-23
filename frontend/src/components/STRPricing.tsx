import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Heading, Button, Select, Table, Thead, Tbody, Tr, Th, Td,
  Text, Badge, useToast, Spinner, Alert, AlertIcon, IconButton
} from '@chakra-ui/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { authenticatedGet, authenticatedPost } from '../services/apiService';

interface PricingRecommendation {
  listing_name: string;
  price_date: string;
  recommended_price: number;
  ai_recommended_adr: number;
  ai_historical_adr: number;
  ai_variance: number;
  ai_reasoning: string;
  is_weekend: boolean;
  event_uplift: number;
  event_name: string;
  last_year_adr: number;
  base_rate: number;
  historical_mult: number;
  occupancy_mult: number;
  pace_mult: number;
  event_mult: number;
  ai_correction: number;
  btw_adjustment: number;
}





const STRPricing: React.FC = () => {
  const [listings, setListings] = useState<string[]>([]);
  const [selectedListing, setSelectedListing] = useState<string>('');
  const [recommendations, setRecommendations] = useState<PricingRecommendation[]>([]);
  const [multipliers, setMultipliers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expandedListings, setExpandedListings] = useState<Set<string>>(new Set());
  const toast = useToast();

  const toggleExpanded = (listing: string) => {
    const newExpanded = new Set(expandedListings);
    if (newExpanded.has(listing)) {
      newExpanded.delete(listing);
    } else {
      newExpanded.add(listing);
    }
    setExpandedListings(newExpanded);
  };

  const loadListings = useCallback(async () => {
    try {
      const response = await authenticatedGet('/api/pricing/listings');
      const data = await response.json();
      if (data.success) {
        setListings(data.listings);
        if (data.listings.length > 0) {
          setSelectedListing(data.listings[0]);
        }
      }
    } catch (error) {
      toast({
        title: 'Error loading listings',
        description: String(error),
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  }, [toast]);

  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authenticatedGet('/api/pricing/recommendations');
      const data = await response.json();
      if (data.success) {
        setRecommendations(data.recommendations);
      }
    } catch (error) {
      toast({
        title: 'Error loading recommendations',
        description: String(error),
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadMultipliers = useCallback(async () => {
    try {
      const response = await authenticatedGet('/api/pricing/multipliers');
      const data = await response.json();
      if (data.success) {
        setMultipliers(data.multipliers);
      }
    } catch (error) {
      toast({
        title: 'Error loading multipliers',
        description: String(error),
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  }, [toast]);

  useEffect(() => {
    loadListings();
    loadRecommendations();
    loadMultipliers();
  }, [loadListings, loadRecommendations, loadMultipliers]);



  const generatePricing = async () => {
    // Allow generating for all listings when selectedListing is empty
    const listingToGenerate = selectedListing || null;

    setGenerating(true);
    try {
      const response = await authenticatedPost('/api/pricing/generate', {
        months: 14,
        listing: listingToGenerate,
      });

      const data = await response.json();
      if (data.success) {
        toast({
          title: 'Pricing generated successfully',
          description: `Generated ${data.result.daily_prices_count} daily prices`,
          status: 'success',
          duration: 5000,
          isClosable: true,
        });
        // Reload data
        loadRecommendations();
        loadMultipliers();
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      toast({
        title: 'Error generating pricing',
        description: String(error),
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setGenerating(false);
    }
  };

  // Filter recommendations by selected listing
  const filteredRecommendations = recommendations.filter(
    rec => selectedListing === '' || rec.listing_name === selectedListing
  );

  // Prepare trend chart data from pricing recommendations only
  const prepareTrendData = () => {
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const trendData: any[] = [];

    // Group pricing recommendations by month
    const monthlyData = new Map<string, {recommended: number[], historical: number[]}>();
    
    filteredRecommendations.forEach(rec => {
      const date = new Date(rec.price_date);
      const monthKey = `${date.getFullYear()}-${date.getMonth() + 1}`;
      
      if (!monthlyData.has(monthKey)) {
        monthlyData.set(monthKey, {recommended: [], historical: []});
      }
      
      const data = monthlyData.get(monthKey)!;
      if (rec.recommended_price && typeof rec.recommended_price === 'number') {
        data.recommended.push(rec.recommended_price);
      }
      if (rec.last_year_adr && typeof rec.last_year_adr === 'number') {
        data.historical.push(rec.last_year_adr);
      }
    });

    // Calculate monthly averages and create chart data
    Array.from(monthlyData.entries())
      .sort(([a], [b]) => {
        const [yearA, monthA] = a.split('-').map(Number);
        const [yearB, monthB] = b.split('-').map(Number);
        return yearA !== yearB ? yearA - yearB : monthA - monthB;
      })
      .forEach(([monthKey, data]) => {
        const [year, month] = monthKey.split('-').map(Number);
        const monthLabel = `${monthNames[month - 1]} ${year}`;
        
        const avgRecommended = data.recommended.length > 0 
          ? data.recommended.reduce((a: number, b: number) => a + b, 0) / data.recommended.length 
          : null;
        const avgHistorical = data.historical.length > 0 
          ? data.historical.reduce((a: number, b: number) => a + b, 0) / data.historical.length 
          : null;

        // Calculate average base rate for the month
        const baseRates: number[] = [];
        filteredRecommendations.forEach(rec => {
          const recDate = new Date(rec.price_date);
          const recMonthKey = `${recDate.getFullYear()}-${recDate.getMonth() + 1}`;
          if (recMonthKey === monthKey && rec.base_rate && typeof rec.base_rate === 'number') {
            baseRates.push(rec.base_rate);
          }
        });
        const avgBaseRate = baseRates.length > 0 
          ? baseRates.reduce((a: number, b: number) => a + b, 0) / baseRates.length 
          : null;

        trendData.push({
          period: monthLabel,
          recommended_adr: avgRecommended ? Number(avgRecommended.toFixed(2)) : null,
          historical_adr: avgHistorical ? Number(avgHistorical.toFixed(2)) : null,
          base_rate: avgBaseRate ? Number(avgBaseRate.toFixed(2)) : null,
        });
      });

    return trendData;
  };

  const trendData = prepareTrendData();

  return (
    <Box p={6} bg="gray.900" minH="100vh" color="white">
      <VStack spacing={6} align="stretch">
        <HStack justify="space-between">
          <Heading color="orange.400" size="lg">💰 STR Pricing Optimizer</Heading>
          <HStack>
            <Select
              value={selectedListing}
              onChange={(e) => setSelectedListing(e.target.value)}
              bg="gray.800"
              borderColor="orange.500"
              color="white"
              w="200px"
            >
              <option value="">All Listings</option>
              {listings.map(listing => (
                <option key={listing} value={listing}>{listing}</option>
              ))}
            </Select>
            <Button
              colorScheme="orange"
              onClick={generatePricing}
              isLoading={generating}
              loadingText="Generating..."
            >
              Generate Pricing
            </Button>
          </HStack>
        </HStack>

        {/* Multiplier Summary Table */}
        <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
          <Heading size="md" mb={4} color="orange.300">Pricing Multipliers Summary</Heading>
          {multipliers.length > 0 ? (
            <Box overflowX="auto">
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th color="orange.300">Listing</Th>
                    <Th color="orange.300" isNumeric>Base Rate</Th>
                    <Th color="orange.300" isNumeric>Historical</Th>
                    <Th color="orange.300" isNumeric>Occupancy</Th>
                    <Th color="orange.300" isNumeric>Revenue Trend</Th>
                    <Th color="orange.300" isNumeric>Event</Th>
                    <Th color="orange.300" isNumeric>AI Correction</Th>
                    <Th color="orange.300" isNumeric>Records</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {multipliers
                    .filter(mult => selectedListing === '' || mult.listing_name === selectedListing)
                    .map((mult, index) => (
                    <Tr key={index}>
                      <Td fontWeight="bold">{mult.listing_name}</Td>
                      <Td isNumeric>€{mult.avg_base_rate?.toFixed(0) || 'N/A'}</Td>
                      <Td isNumeric>{mult.avg_historical_mult?.toFixed(3) || 'N/A'}x</Td>
                      <Td isNumeric>{mult.avg_occupancy_mult?.toFixed(3) || 'N/A'}x</Td>
                      <Td isNumeric>{mult.avg_pace_mult?.toFixed(3) || 'N/A'}x</Td>
                      <Td isNumeric>{mult.avg_event_mult?.toFixed(3) || 'N/A'}x</Td>
                      <Td isNumeric>{mult.avg_ai_correction?.toFixed(3) || 'N/A'}x</Td>
                      <Td isNumeric>{mult.record_count || 0}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </Box>
          ) : (
            <Text color="gray.400">No multiplier data available. Generate pricing to see multipliers.</Text>
          )}
        </Box>

        {/* Trend Chart */}
        <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
          <Heading size="md" mb={4} color="orange.300">Historical vs Recommended ADR Trend</Heading>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#4A5568" />
                <XAxis dataKey="period" stroke="#E2E8F0" />
                <YAxis stroke="#E2E8F0" />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#2D3748', border: '1px solid #ED8936' }}
                  labelStyle={{ color: '#E2E8F0' }}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="historical_adr" 
                  stroke="#4299E1" 
                  strokeWidth={2}
                  name="Historical ADR"
                  connectNulls={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="recommended_adr" 
                  stroke="#ED8936" 
                  strokeWidth={2}
                  name="Recommended ADR"
                  connectNulls={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="base_rate" 
                  stroke="#68D391" 
                  strokeWidth={2}
                  name="Base Rate"
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <Text color="gray.400">No trend data available</Text>
          )}
        </Box>

        {/* Monthly Multipliers Table */}
        <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
          <Heading size="md" mb={4} color="orange.300">Monthly Multipliers by Listing</Heading>
          {recommendations.length > 0 ? (
            <Box overflowX="auto">
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th color="orange.300">Listing</Th>
                    <Th color="orange.300" isNumeric>Base Rate</Th>
                    <Th color="orange.300" isNumeric>Historical</Th>
                    <Th color="orange.300" isNumeric>Occupancy</Th>
                    <Th color="orange.300" isNumeric>Pace</Th>
                    <Th color="orange.300" isNumeric>Event</Th>
                    <Th color="orange.300" isNumeric>AI Correction</Th>
                    <Th color="orange.300" isNumeric>BTW</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {(() => {
                    // Group recommendations by listing and calculate monthly averages
                    const listingAverages = new Map();
                    const listingMonthlyData = new Map();
                    
                    const dataToProcess = selectedListing ? 
                      recommendations.filter(rec => rec.listing_name === selectedListing) : 
                      recommendations;
                    
                    dataToProcess.forEach(rec => {
                      const listing = rec.listing_name;
                      const month = new Date(rec.price_date).getMonth() + 1;
                      const monthName = new Date(rec.price_date).toLocaleDateString('en-US', { month: 'short' });
                      
                      if (!listingAverages.has(listing)) {
                        listingAverages.set(listing, {
                          base_rate: [],
                          historical_mult: [],
                          occupancy_mult: [],
                          pace_mult: [],
                          event_mult: [],
                          ai_correction: [],
                          btw_adjustment: []
                        });
                        listingMonthlyData.set(listing, new Map());
                      }
                      
                      const data = listingAverages.get(listing);
                      const monthlyData = listingMonthlyData.get(listing);
                      
                      if (!monthlyData.has(month)) {
                        monthlyData.set(month, {
                          monthName,
                          base_rate: [],
                          historical_mult: [],
                          occupancy_mult: [],
                          pace_mult: [],
                          event_mult: [],
                          ai_correction: [],
                          btw_adjustment: []
                        });
                      }
                      
                      const monthData = monthlyData.get(month);
                      
                      if (rec.base_rate) {
                        data.base_rate.push(rec.base_rate);
                        monthData.base_rate.push(rec.base_rate);
                      }
                      if (rec.historical_mult) {
                        data.historical_mult.push(rec.historical_mult);
                        monthData.historical_mult.push(rec.historical_mult);
                      }
                      if (rec.occupancy_mult) {
                        data.occupancy_mult.push(rec.occupancy_mult);
                        monthData.occupancy_mult.push(rec.occupancy_mult);
                      }
                      if (rec.pace_mult) {
                        data.pace_mult.push(rec.pace_mult);
                        monthData.pace_mult.push(rec.pace_mult);
                      }
                      if (rec.event_mult) {
                        data.event_mult.push(rec.event_mult);
                        monthData.event_mult.push(rec.event_mult);
                      }
                      if (rec.ai_correction) {
                        data.ai_correction.push(rec.ai_correction);
                        monthData.ai_correction.push(rec.ai_correction);
                      }
                      if (rec.btw_adjustment) {
                        data.btw_adjustment.push(rec.btw_adjustment);
                        monthData.btw_adjustment.push(rec.btw_adjustment);
                      }
                    });
                    
                    const rows: React.ReactElement[] = [];
                    
                    Array.from(listingAverages.entries()).forEach(([listing, data]) => {
                      const avgBaseRate = data.base_rate.length > 0 ? 
                        data.base_rate.reduce((a: number, b: number) => a + b, 0) / data.base_rate.length : 0;
                      const avgHistorical = data.historical_mult.length > 0 ? 
                        data.historical_mult.reduce((a: number, b: number) => a + b, 0) / data.historical_mult.length : 0;
                      const avgOccupancy = data.occupancy_mult.length > 0 ? 
                        data.occupancy_mult.reduce((a: number, b: number) => a + b, 0) / data.occupancy_mult.length : 0;
                      const avgPace = data.pace_mult.length > 0 ? 
                        data.pace_mult.reduce((a: number, b: number) => a + b, 0) / data.pace_mult.length : 0;
                      const avgEvent = data.event_mult.length > 0 ? 
                        data.event_mult.reduce((a: number, b: number) => a + b, 0) / data.event_mult.length : 0;
                      const avgAI = data.ai_correction.length > 0 ? 
                        data.ai_correction.reduce((a: number, b: number) => a + b, 0) / data.ai_correction.length : 0;
                      const avgBTW = data.btw_adjustment.length > 0 ? 
                        data.btw_adjustment.reduce((a: number, b: number) => a + b, 0) / data.btw_adjustment.length : 0;
                      
                      const monthlyData = listingMonthlyData.get(listing);
                      const isExpanded = expandedListings.has(listing);
                      
                      // Main listing row
                      rows.push(
                        <Tr key={listing}>
                          <Td>
                            <HStack>
                              <IconButton
                                size="xs"
                                variant="solid"
                                colorScheme="orange"
                                bg="orange.600"
                                color="white"
                                _hover={{ bg: "orange.500" }}
                                children={isExpanded ? '▼' : '▶'}
                                onClick={() => toggleExpanded(listing)}
                                aria-label="Toggle monthly details"
                              />
                              <Text fontWeight="bold">{listing}</Text>
                            </HStack>
                          </Td>
                          <Td isNumeric>€{avgBaseRate.toFixed(0)}</Td>
                          <Td isNumeric>{avgHistorical.toFixed(3)}x</Td>
                          <Td isNumeric>{avgOccupancy.toFixed(3)}x</Td>
                          <Td isNumeric>{avgPace.toFixed(3)}x</Td>
                          <Td isNumeric>{avgEvent.toFixed(3)}x</Td>
                          <Td isNumeric>{avgAI.toFixed(3)}x</Td>
                          <Td isNumeric>{avgBTW.toFixed(3)}x</Td>
                        </Tr>
                      );
                      
                      // Monthly detail rows
                      if (isExpanded) {
                        const monthlyOptions = Array.from(monthlyData.entries())
                          .sort((a: any, b: any) => a[0] - b[0])
                          .map((entry: any) => {
                            const [, monthData] = entry;
                            return {
                              month: monthData.monthName,
                              base_rate: monthData.base_rate.length > 0 ? monthData.base_rate.reduce((a: number, b: number) => a + b, 0) / monthData.base_rate.length : 0,
                              historical: monthData.historical_mult.length > 0 ? monthData.historical_mult.reduce((a: number, b: number) => a + b, 0) / monthData.historical_mult.length : 0,
                              occupancy: monthData.occupancy_mult.length > 0 ? monthData.occupancy_mult.reduce((a: number, b: number) => a + b, 0) / monthData.occupancy_mult.length : 0,
                              pace: monthData.pace_mult.length > 0 ? monthData.pace_mult.reduce((a: number, b: number) => a + b, 0) / monthData.pace_mult.length : 0,
                              event: monthData.event_mult.length > 0 ? monthData.event_mult.reduce((a: number, b: number) => a + b, 0) / monthData.event_mult.length : 0,
                              ai: monthData.ai_correction.length > 0 ? monthData.ai_correction.reduce((a: number, b: number) => a + b, 0) / monthData.ai_correction.length : 0,
                              btw: monthData.btw_adjustment.length > 0 ? monthData.btw_adjustment.reduce((a: number, b: number) => a + b, 0) / monthData.btw_adjustment.length : 0
                            };
                          });
                        
                        monthlyOptions.forEach((monthData) => {
                          rows.push(
                            <Tr key={`${listing}-${monthData.month}`} bg="gray.750">
                              <Td pl={12} fontSize="sm" color="gray.400">{monthData.month}</Td>
                              <Td isNumeric fontSize="sm">€{monthData.base_rate.toFixed(0)}</Td>
                              <Td isNumeric fontSize="sm">{monthData.historical.toFixed(3)}x</Td>
                              <Td isNumeric fontSize="sm">{monthData.occupancy.toFixed(3)}x</Td>
                              <Td isNumeric fontSize="sm">{monthData.pace.toFixed(3)}x</Td>
                              <Td isNumeric fontSize="sm">{monthData.event.toFixed(3)}x</Td>
                              <Td isNumeric fontSize="sm">{monthData.ai.toFixed(3)}x</Td>
                              <Td isNumeric fontSize="sm">{monthData.btw.toFixed(3)}x</Td>
                            </Tr>
                          );
                        });
                      }
                    });
                    
                    return rows;
                  })()
                  }
                </Tbody>
              </Table>
            </Box>
          ) : (
            <Text color="gray.400">No data available for multipliers analysis</Text>
          )}
        </Box>

        {/* Quarterly Summary Table */}
        <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
          <Heading size="md" mb={4} color="orange.300">Quarterly Summary</Heading>
          {recommendations.length > 0 ? (
            <Box overflowX="auto">
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th color="orange.300">Quarter</Th>
                    {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                      <Th key={listing} color="orange.300" textAlign="center">{listing}</Th>
                    ))}
                  </Tr>
                  <Tr>
                    <Th></Th>
                    {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                      <Th key={listing} color="gray.400" fontSize="xs" textAlign="center">Rec | Hist</Th>
                    ))}
                  </Tr>
                </Thead>
                <Tbody>
                  {(() => {
                    type QuarterlyDataType = {[key: string]: {rec: number[], hist: number[]}};
                    const quarterlyData = new Map<string, QuarterlyDataType>();
                    
                    const dataToProcess = selectedListing ? 
                      recommendations.filter(rec => rec.listing_name === selectedListing) : 
                      recommendations;
                    
                    dataToProcess.forEach(rec => {
                      const date = new Date(rec.price_date);
                      const quarter = `${date.getFullYear()} Q${Math.ceil((date.getMonth() + 1) / 3)}`;
                      
                      // Skip quarters more than 1 year ahead
                      const oneYearFromNow = new Date();
                      oneYearFromNow.setFullYear(oneYearFromNow.getFullYear() + 1);
                      if (date > oneYearFromNow) return;
                      
                      if (!quarterlyData.has(quarter)) {
                        quarterlyData.set(quarter, {
                          'Green Studio': {rec: [], hist: []},
                          'Red Studio': {rec: [], hist: []},
                          'Child Friendly': {rec: [], hist: []}
                        });
                      }
                      
                      const qData = quarterlyData.get(quarter)!;
                      if (qData[rec.listing_name]) {
                        if (rec.recommended_price) qData[rec.listing_name].rec.push(rec.recommended_price);
                        if (rec.last_year_adr) qData[rec.listing_name].hist.push(rec.last_year_adr);
                      }
                    });
                    
                    const quarters = Array.from(quarterlyData.keys()).sort();
                    const totals: {[key: string]: {rec: number, hist: number}} = {
                      'Green Studio': {rec: 0, hist: 0}, 
                      'Red Studio': {rec: 0, hist: 0}, 
                      'Child Friendly': {rec: 0, hist: 0}
                    };
                    
                    return [
                      ...quarters.map(quarter => {
                        const qData = quarterlyData.get(quarter)!;
                        const listings = selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly'];
                        
                        return (
                          <Tr key={quarter}>
                            <Td fontWeight="bold">{quarter}</Td>
                            {listings.map(listing => {
                              const avgRec = qData[listing].rec.length > 0 
                                ? qData[listing].rec.reduce((a: number, b: number) => a + b, 0) / qData[listing].rec.length 
                                : 0;
                              const avgHist = qData[listing].hist.length > 0 
                                ? qData[listing].hist.reduce((a: number, b: number) => a + b, 0) / qData[listing].hist.length 
                                : 0;
                              
                              totals[listing].rec += avgRec;
                              totals[listing].hist += avgHist;
                              
                              return (
                                <Td key={listing} textAlign="center">
                                  <Text fontSize="sm">
                                    €{avgRec.toFixed(0)} | €{avgHist.toFixed(0)}
                                  </Text>
                                </Td>
                              );
                            })}
                          </Tr>
                        );
                      }),
                      <Tr key="total" bg="orange.900">
                        <Td fontWeight="bold" color="orange.300">TOTAL</Td>
                        {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                          <Td key={listing} textAlign="center" fontWeight="bold" color="orange.300">
                            €{totals[listing].rec.toFixed(0)} | €{totals[listing].hist.toFixed(0)}
                          </Td>
                        ))}
                      </Tr>
                    ];
                  })()}
                </Tbody>
              </Table>
            </Box>
          ) : (
            <Text color="gray.400">No data available for quarterly summary</Text>
          )}
        </Box>

        {/* Pricing Recommendations Table */}
        <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
          <Heading size="md" mb={4} color="orange.300">
            Pricing Recommendations {selectedListing && `- ${selectedListing}`}
          </Heading>
          
          {loading ? (
            <HStack justify="center" p={8}>
              <Spinner color="orange.400" />
              <Text>Loading recommendations...</Text>
            </HStack>
          ) : filteredRecommendations.length === 0 ? (
            <Alert status="info">
              <AlertIcon />
              No pricing recommendations found. Generate pricing for a listing to see recommendations.
            </Alert>
          ) : (
            <Box overflowX="auto">
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th color="orange.300">Listing</Th>
                    <Th color="orange.300">Date</Th>
                    <Th color="orange.300" isNumeric>Recommended</Th>
                    <Th color="orange.300" isNumeric>AI Rec</Th>
                    <Th color="orange.300" isNumeric>Historical</Th>
                    <Th color="orange.300" isNumeric>Variance</Th>
                    <Th color="orange.300">Weekend</Th>
                    <Th color="orange.300">Event</Th>
                    <Th color="orange.300">AI Reasoning</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {filteredRecommendations.slice(0, 50).map((rec, index) => (
                    <Tr key={index}>
                      <Td>{rec.listing_name}</Td>
                      <Td>{new Date(rec.price_date).toLocaleDateString()}</Td>
                      <Td isNumeric>
                        <Text fontWeight="bold" color="orange.300">
                          €{rec.recommended_price && typeof rec.recommended_price === 'number' ? rec.recommended_price.toFixed(2) : 'N/A'}
                        </Text>
                      </Td>
                      <Td isNumeric>€{rec.ai_recommended_adr && typeof rec.ai_recommended_adr === 'number' ? rec.ai_recommended_adr.toFixed(2) : 'N/A'}</Td>
                      <Td isNumeric>€{rec.last_year_adr && typeof rec.last_year_adr === 'number' ? rec.last_year_adr.toFixed(2) : 'N/A'}</Td>
                      <Td isNumeric>
                        {rec.ai_variance && typeof rec.ai_variance === 'number' ? (
                          <Badge colorScheme={rec.ai_variance > 0 ? 'green' : 'red'}>
                            {rec.ai_variance > 0 ? '+' : ''}{rec.ai_variance.toFixed(1)}%
                          </Badge>
                        ) : 'N/A'}
                      </Td>
                      <Td>
                        {rec.is_weekend ? (
                          <Badge colorScheme="purple">Weekend</Badge>
                        ) : (
                          <Badge colorScheme="gray">Weekday</Badge>
                        )}
                      </Td>
                      <Td>
                        {rec.event_name ? (
                          <Badge colorScheme="yellow" fontSize="xs">
                            {rec.event_name}
                          </Badge>
                        ) : '-'}
                      </Td>
                      <Td maxW="200px">
                        <Text fontSize="xs" color="gray.300" noOfLines={2}>
                          {rec.ai_reasoning || 'No reasoning provided'}
                        </Text>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
              {filteredRecommendations.length > 50 && (
                <Text mt={2} color="gray.400" fontSize="sm">
                  Showing first 50 of {filteredRecommendations.length} recommendations
                </Text>
              )}
            </Box>
          )}
        </Box>
      </VStack>
    </Box>
  );
};

export default STRPricing;