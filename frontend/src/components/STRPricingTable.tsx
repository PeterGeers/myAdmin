/**
 * STRPricingTable Component
 *
 * Pricing recommendations table and quarterly summary for the STR Pricing page.
 */

import React from 'react';
import {
  Box, HStack, Text, Heading, Badge, Alert, AlertIcon, Spinner,
  Table, Thead, Tbody, Tr, Th, Td,
} from '@chakra-ui/react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PricingRecommendation {
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

interface STRPricingTableProps {
  recommendations: PricingRecommendation[];
  selectedListing: string;
  loading: boolean;
  t: (key: string) => string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const STRPricingTable: React.FC<STRPricingTableProps> = ({
  recommendations, selectedListing, loading, t,
}) => {
  const filteredRecommendations = selectedListing
    ? recommendations.filter(r => r.listing_name === selectedListing)
    : recommendations;

  return (
    <>
      {/* Quarterly Summary Table */}
      <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
        <Heading size="md" mb={4} color="orange.300">{t('pricing.quarterlySummary.title')}</Heading>
        {recommendations.length > 0 ? (
          <Box overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th color="orange.300">{t('pricing.quarterlySummary.quarter')}</Th>
                  {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                    <Th key={listing} color="orange.300" textAlign="center">{listing}</Th>
                  ))}
                </Tr>
                <Tr>
                  <Th></Th>
                  {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                    <Th key={listing} color="gray.400" fontSize="xs" textAlign="center">{t('pricing.quarterlySummary.recHist')}</Th>
                  ))}
                </Tr>
              </Thead>
              <Tbody>
                {(() => {
                  type QuarterlyDataType = {[key: string]: {rec: number[], hist: number[]}};
                  const quarterlyData = new Map<string, QuarterlyDataType>();
                  const dataToProcess = selectedListing
                    ? recommendations.filter(rec => rec.listing_name === selectedListing)
                    : recommendations;

                  dataToProcess.forEach(rec => {
                    const date = new Date(rec.price_date);
                    const quarter = `${date.getFullYear()} Q${Math.ceil((date.getMonth() + 1) / 3)}`;
                    const oneYearFromNow = new Date();
                    oneYearFromNow.setFullYear(oneYearFromNow.getFullYear() + 1);
                    if (date > oneYearFromNow) return;

                    if (!quarterlyData.has(quarter)) {
                      quarterlyData.set(quarter, {
                        'Green Studio': {rec: [], hist: []},
                        'Red Studio': {rec: [], hist: []},
                        'Child Friendly': {rec: [], hist: []},
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
                    'Child Friendly': {rec: 0, hist: 0},
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
                              ? qData[listing].rec.reduce((a: number, b: number) => a + b, 0) / qData[listing].rec.length : 0;
                            const avgHist = qData[listing].hist.length > 0
                              ? qData[listing].hist.reduce((a: number, b: number) => a + b, 0) / qData[listing].hist.length : 0;
                            totals[listing].rec += avgRec;
                            totals[listing].hist += avgHist;
                            return (
                              <Td key={listing} textAlign="center">
                                <Text fontSize="sm">€{avgRec.toFixed(0)} | €{avgHist.toFixed(0)}</Text>
                              </Td>
                            );
                          })}
                        </Tr>
                      );
                    }),
                    <Tr key="total" bg="orange.900">
                      <Td fontWeight="bold" color="orange.300">{t('pricing.quarterlySummary.total')}</Td>
                      {(selectedListing ? [selectedListing] : ['Green Studio', 'Red Studio', 'Child Friendly']).map(listing => (
                        <Td key={listing} textAlign="center" fontWeight="bold" color="orange.300">
                          €{totals[listing].rec.toFixed(0)} | €{totals[listing].hist.toFixed(0)}
                        </Td>
                      ))}
                    </Tr>,
                  ];
                })()}
              </Tbody>
            </Table>
          </Box>
        ) : (
          <Text color="gray.400">{t('pricing.quarterlySummary.noData')}</Text>
        )}
      </Box>

      {/* Pricing Recommendations Table */}
      <Box bg="gray.800" p={4} borderRadius="md" borderColor="orange.500" borderWidth="1px">
        <Heading size="md" mb={4} color="orange.300">
          {t('pricing.recommendations.title')} {selectedListing && `- ${selectedListing}`}
        </Heading>

        {loading ? (
          <HStack justify="center" p={8}>
            <Spinner color="orange.400" />
            <Text>{t('pricing.recommendations.loading')}</Text>
          </HStack>
        ) : filteredRecommendations.length === 0 ? (
          <Alert status="info"><AlertIcon />{t('pricing.recommendations.noData')}</Alert>
        ) : (
          <Box overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th color="orange.300">{t('pricing.multipliersSummary.listing')}</Th>
                  <Th color="orange.300">{t('pricing.recommendations.date')}</Th>
                  <Th color="orange.300" isNumeric>{t('pricing.recommendations.recommended')}</Th>
                  <Th color="orange.300" isNumeric>{t('pricing.recommendations.aiRecommended')}</Th>
                  <Th color="orange.300" isNumeric>{t('pricing.recommendations.historical')}</Th>
                  <Th color="orange.300" isNumeric>{t('pricing.recommendations.variance')}</Th>
                  <Th color="orange.300">{t('pricing.recommendations.weekend')}</Th>
                  <Th color="orange.300">{t('pricing.recommendations.event')}</Th>
                  <Th color="orange.300">{t('pricing.recommendations.reasoning')}</Th>
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
                        <Badge colorScheme="purple">{t('pricing.recommendations.weekend')}</Badge>
                      ) : (
                        <Badge colorScheme="gray">{t('pricing.recommendations.weekday')}</Badge>
                      )}
                    </Td>
                    <Td>
                      {rec.event_name ? (
                        <Badge colorScheme="yellow" fontSize="xs">{rec.event_name}</Badge>
                      ) : '-'}
                    </Td>
                    <Td maxW="200px">
                      <Text fontSize="xs" color="gray.300" noOfLines={2}>
                        {rec.ai_reasoning || t('pricing.recommendations.noData')}
                      </Text>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
            {filteredRecommendations.length > 50 && (
              <Text mt={2} color="gray.400" fontSize="sm">
                Showing first 50 of {filteredRecommendations.length} {t('pricing.recommendations.title').toLowerCase()}
              </Text>
            )}
          </Box>
        )}
      </Box>
    </>
  );
};
