/**
 * STRSummaryPanel Component
 *
 * Displays a summary card with booking totals and channel breakdown,
 * plus the payout import results panel.
 */

import React from 'react';
import {
  Box, Text, HStack, Badge, Grid, GridItem,
  Card, CardBody, CardHeader, Heading,
} from '@chakra-ui/react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface STRSummary {
  total_bookings: number;
  total_nights: number;
  total_gross: number;
  channels: { [key: string]: number };
}

interface PayoutResult {
  processing: { total_rows: number; reservation_rows: number; updates_prepared: number };
  summary: { total_updated: number; total_not_found: number; total_errors: number };
  database: { not_found?: string[]; errors?: string[] };
}

interface STRSummaryPanelProps {
  summary: STRSummary | null;
  t: (key: string, params?: Record<string, unknown>) => string;
}

interface STRPayoutResultsPanelProps {
  payoutResult: PayoutResult;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Summary Card
// ---------------------------------------------------------------------------

export const STRSummaryPanel: React.FC<STRSummaryPanelProps> = ({ summary, t }) => {
  if (!summary) return null;

  return (
    <Card bg="gray.700">
      <CardHeader>
        <Heading size="md" color="white">{t('processor.summary.title')}</Heading>
      </CardHeader>
      <CardBody>
        <Grid templateColumns="repeat(4, 1fr)" gap={4}>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.summary.totalBookings')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">{summary.total_bookings}</Text>
          </GridItem>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.summary.totalNights')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">{summary.total_nights}</Text>
          </GridItem>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.summary.totalGross')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">
              €{summary.total_gross ? summary.total_gross.toFixed(2) : '0.00'}
            </Text>
          </GridItem>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.summary.channels')}</Text>
            <HStack wrap="wrap">
              {summary.channels && Object.entries(summary.channels).map(([channel, count]) => (
                <Badge key={channel} colorScheme="green">{channel}: {count}</Badge>
              ))}
            </HStack>
          </GridItem>
        </Grid>
      </CardBody>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Payout Results Card
// ---------------------------------------------------------------------------

export const STRPayoutResultsPanel: React.FC<STRPayoutResultsPanelProps> = ({ payoutResult, t }) => {
  return (
    <Card bg="gray.600" borderColor="purple.500" borderWidth="2px">
      <CardHeader>
        <Heading size="sm" color="white">{t('processor.payoutResults.title')}</Heading>
      </CardHeader>
      <CardBody>
        <Grid templateColumns="repeat(3, 1fr)" gap={4} mb={4}>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.totalRows')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">{payoutResult.processing.total_rows}</Text>
          </GridItem>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.reservations')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">{payoutResult.processing.reservation_rows}</Text>
          </GridItem>
          <GridItem>
            <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.updatesPrepared')}</Text>
            <Text color="white" fontSize="xl" fontWeight="bold">{payoutResult.processing.updates_prepared}</Text>
          </GridItem>
        </Grid>

        <Grid templateColumns="repeat(3, 1fr)" gap={4}>
          <GridItem>
            <Badge colorScheme="green" fontSize="md" p={2}>
              ✓ {t('processor.payoutResults.updated')}: {payoutResult.summary.total_updated}
            </Badge>
          </GridItem>
          <GridItem>
            <Badge colorScheme="orange" fontSize="md" p={2}>
              ⚠ {t('processor.payoutResults.notFound')}: {payoutResult.summary.total_not_found}
            </Badge>
          </GridItem>
          <GridItem>
            <Badge colorScheme="red" fontSize="md" p={2}>
              ✗ {t('processor.payoutResults.errors')}: {payoutResult.summary.total_errors}
            </Badge>
          </GridItem>
        </Grid>

        {payoutResult.database.not_found && payoutResult.database.not_found.length > 0 && (
          <Box mt={4}>
            <Text color="gray.300" fontSize="sm" fontWeight="bold" mb={2}>
              {t('processor.payoutResults.notFoundInDatabase')}
            </Text>
            <Box bg="gray.700" p={3} borderRadius="md" maxH="150px" overflowY="auto">
              {payoutResult.database.not_found.slice(0, 10).map((code, idx) => (
                <Text key={idx} color="orange.300" fontSize="xs">• {code}</Text>
              ))}
              {payoutResult.database.not_found.length > 10 && (
                <Text color="gray.400" fontSize="xs" mt={2}>
                  {t('processor.payoutResults.andMore', { count: payoutResult.database.not_found.length - 10 })}
                </Text>
              )}
            </Box>
            <Text color="gray.400" fontSize="xs" mt={2}>
              {t('processor.payoutResults.mayBeCancelled')}
            </Text>
          </Box>
        )}

        {payoutResult.database.errors && payoutResult.database.errors.length > 0 && (
          <Box mt={4}>
            <Text color="red.300" fontSize="sm" fontWeight="bold" mb={2}>
              {t('processor.payoutResults.errorsList')}
            </Text>
            <Box bg="red.900" p={3} borderRadius="md">
              {payoutResult.database.errors.map((error, idx) => (
                <Text key={idx} color="red.200" fontSize="xs">• {error}</Text>
              ))}
            </Box>
          </Box>
        )}
      </CardBody>
    </Card>
  );
};
