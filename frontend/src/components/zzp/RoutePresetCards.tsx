import React from 'react';
import { Box, Grid, Text, Badge, HStack } from '@chakra-ui/react';
import type { RoutePreset } from '../../types/zzpTrips';

interface RoutePresetCardsProps {
  presets: RoutePreset[];
  onSelect: (preset: RoutePreset) => void;
  selectedId?: number | null;
}

/**
 * Touch-friendly card grid for route presets.
 * Displays a 2-column grid on mobile, 3-4 on wider screens.
 * Each card shows: from → to, category badge, typical km.
 */
export const RoutePresetCards: React.FC<RoutePresetCardsProps> = ({
  presets,
  onSelect,
  selectedId,
}) => {
  if (presets.length === 0) {
    return (
      <Box p={4} bg="gray.700" borderRadius="md" textAlign="center">
        <Text color="gray.400" fontSize="sm">
          Geen route presets beschikbaar
        </Text>
      </Box>
    );
  }

  const getCategoryColor = (category: string | null): string => {
    switch (category) {
      case 'Zakelijk':
        return 'green';
      case 'Woon-werk':
        return 'blue';
      case 'Privé':
        return 'gray';
      default:
        return 'orange';
    }
  };

  return (
    <Grid
      templateColumns={{ base: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)', lg: 'repeat(4, 1fr)' }}
      gap={3}
    >
      {presets.map((preset) => (
        <Box
          key={preset.id}
          p={3}
          borderRadius="md"
          bg={selectedId === preset.id ? 'orange.700' : 'gray.700'}
          borderWidth="2px"
          borderColor={selectedId === preset.id ? 'orange.400' : 'transparent'}
          _hover={{ bg: selectedId === preset.id ? 'orange.600' : 'gray.600' }}
          _active={{ bg: 'orange.700' }}
          cursor="pointer"
          onClick={() => onSelect(preset)}
          minH="44px"
          display="flex"
          flexDirection="column"
          justifyContent="center"
          transition="all 0.15s ease"
          role="button"
          tabIndex={0}
          aria-label={`Route: ${preset.from_address} naar ${preset.to_address}`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(preset);
            }
          }}
        >
          <Text fontSize="sm" fontWeight="medium" color="white" noOfLines={1}>
            {preset.from_address}
          </Text>
          <Text fontSize="sm" color="orange.200" mt={0.5}>
            → {preset.to_address}
          </Text>
          <HStack mt={2} spacing={2} flexWrap="wrap">
            {preset.default_category && (
              <Badge
                colorScheme={getCategoryColor(preset.default_category)}
                fontSize="xs"
                variant="subtle"
              >
                {preset.default_category}
              </Badge>
            )}
            {preset.default_purpose && (
              <Text fontSize="xs" color="gray.300">
                {preset.default_purpose}
              </Text>
            )}
            {preset.typical_distance_km && (
              <Text fontSize="xs" color="gray.400">
                ~{preset.typical_distance_km} km
              </Text>
            )}
          </HStack>
        </Box>
      ))}
    </Grid>
  );
};

export default RoutePresetCards;
