/**
 * BijtellingWidget — Progress bar for tracking private km usage toward 500 km/year bijtelling threshold.
 * Only rendered for business vehicles.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.2
 */

import React from 'react';
import { Box, Flex, Text, Progress } from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import type { TripSummary } from '../../types/zzpTrips';

interface BijtellingWidgetProps {
  summary: TripSummary | null;
  vehicleType: 'private_for_business' | 'business' | undefined;
}

/**
 * Displays a progress bar showing private km usage relative to the bijtelling limit (500 km/year).
 * Color-coded: green (safe) → yellow (approaching) → red (exceeded).
 */
export const BijtellingWidget: React.FC<BijtellingWidgetProps> = ({ summary, vehicleType }) => {
  const { t } = useTypedTranslation('zzp');

  // Only render for business vehicles with summary data
  if (vehicleType !== 'business' || !summary) return null;

  // Calculate progress toward limit
  const privateKm = summary.bijtelling_km; // privé + woon-werk combined
  const limit = summary.bijtelling_limit || 500;
  const percentage = Math.min((privateKm / limit) * 100, 100);
  const remaining = Math.max(limit - privateKm, 0);
  const isWarning = summary.bijtelling_warning; // true when approaching threshold
  const isExceeded = privateKm >= limit;

  // Color logic: green → yellow → red
  const barColorScheme = isExceeded ? 'red' : isWarning ? 'yellow' : 'green';

  return (
    <Box bg="gray.700" p={3} borderRadius="md" mb={4}>
      <Flex justify="space-between" align="center" mb={2}>
        <Text fontSize="sm" color="gray.300">
          {t('trips.bijtelling.title')}
        </Text>
        <Text fontSize="sm" color="white" fontWeight="bold">
          {privateKm} / {limit} km
        </Text>
      </Flex>

      <Progress
        value={percentage}
        colorScheme={barColorScheme}
        size="sm"
        borderRadius="md"
      />

      <Text fontSize="xs" color="gray.400" mt={1}>
        {isExceeded
          ? t('trips.bijtelling.exceeded')
          : t('trips.bijtelling.remainingKm', { remaining })}
      </Text>

      {isWarning && !isExceeded && (
        <Text fontSize="xs" color="yellow.300" mt={1}>
          ⚠️ {t('trips.bijtelling.warningMessage')}
        </Text>
      )}
    </Box>
  );
};

export default BijtellingWidget;
