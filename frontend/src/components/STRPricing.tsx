import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Heading, Button, Select, Table, Thead, Tbody, Tr, Th, Td,
  Text, Badge, useToast, Spinner, Alert, AlertIcon
} from '@chakra-ui/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

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
}



const STRPricing: React.FC = () => {
  const [listings, setListings] = useState<string[]>([]);
  const [selectedListing, setSelectedListing] = useState<string>('');
  const [recommendations, setRecommendations] = useState<PricingRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const toast = useToast();

  const loadListings = useCallback(async () => {
    try {
      const response = await fetch('/api/pricing/listings');
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
      const response = await fetch('/api/pricing/recommendations');
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

  useEffect(() => {
    loadListings();
    loadRecommendations();
  }, [loadListings, loadRecommendations]);



  const generatePricing = async () => {
    if (!selectedListing) {
      toast({
        title: 'No listing selected',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setGenerating(true);
    try {
      const response = await fetch('/api/pricing/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          months: 14,
          listing: selectedListing,
        }),
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

        trendData.push({
          period: monthLabel,
          recommended_adr: avgRecommended ? Number(avgRecommended.toFixed(2)) : null,
          historical_adr: avgHistorical ? Number(avgHistorical.toFixed(2)) : null,
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
              isDisabled={!selectedListing}
            >
              Generate Pricing
            </Button>
          </HStack>
        </HStack>

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
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <Text color="gray.400">No trend data available</Text>
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