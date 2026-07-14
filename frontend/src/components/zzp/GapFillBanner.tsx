/**
 * GapFillBanner — warning banner shown when a gap is detected after trip creation.
 * Offers user the option to accept the gap-fill (creates a gap-fill trip) or dismiss.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.2
 */

import React, { useState } from 'react';
import { Box, Flex, Text, Button, useToast } from '@chakra-ui/react';
import { WarningIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { createGapFill } from '../../services/tripService';
import type { GapFillData } from '../../types/zzpTrips';

export interface GapFillBannerProps {
  gapFillOffer: {
    start_odometer: number;
    end_odometer: number;
    suggested_category: string;
    suggested_purpose: string;
  } | null;
  gapWarning: {
    gap_km: number;
    previous_end_odometer: number;
    current_start_odometer: number;
    message: string;
  } | null;
  vehicleId: number;
  onAccepted: () => void;
}

export const GapFillBanner: React.FC<GapFillBannerProps> = ({
  gapFillOffer,
  gapWarning,
  vehicleId,
  onAccepted,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(false);

  // Don't render if no offer/warning or already dismissed
  if (!gapFillOffer || !gapWarning || dismissed) {
    return null;
  }

  const handleAccept = async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().split('T')[0];
      const data: GapFillData = {
        vehicle_id: vehicleId,
        trip_date: today,
        start_odometer: gapFillOffer.start_odometer,
        end_odometer: gapFillOffer.end_odometer,
        start_address: 'Onbekend',
        end_address: 'Onbekend',
        trip_category: gapFillOffer.suggested_category,
        trip_purpose: gapFillOffer.suggested_purpose,
      };
      const resp = await createGapFill(data);
      if (resp.success) {
        toast({
          title: t('trips.gapFill.accepted'),
          status: 'success',
          duration: 3000,
        });
        onAccepted();
      } else {
        throw new Error(resp.warnings?.[0]?.message || 'Unknown error');
      }
    } catch (err) {
      toast({
        title: t('trips.gapFill.error'),
        description: err instanceof Error ? err.message : undefined,
        status: 'error',
        duration: 4000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDismiss = () => {
    setDismissed(true);
  };

  return (
    <Box
      bg="orange.900"
      borderLeft="4px solid"
      borderLeftColor="yellow.400"
      borderRadius="md"
      p={3}
      mb={4}
    >
      <Flex align="center" justify="space-between" wrap="wrap" gap={2}>
        <Flex align="center" gap={2} flex="1">
          <WarningIcon color="yellow.300" />
          <Text color="yellow.200" fontSize="sm" fontWeight="medium">
            {t('trips.gapFill.bannerMessage', {
              km: gapWarning.gap_km,
              from: gapWarning.previous_end_odometer,
              to: gapWarning.current_start_odometer,
            })}
          </Text>
        </Flex>
        <Flex gap={2}>
          <Button
            size="sm"
            colorScheme="yellow"
            variant="solid"
            isLoading={loading}
            onClick={handleAccept}
          >
            {t('trips.gapFill.accept')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            color="yellow.200"
            _hover={{ bg: 'orange.800' }}
            onClick={handleDismiss}
          >
            {t('trips.gapFill.dismiss')}
          </Button>
        </Flex>
      </Flex>
    </Box>
  );
};

export default GapFillBanner;
