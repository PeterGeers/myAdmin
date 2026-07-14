import React, { useState } from 'react';
import { Box, Flex, Text, Badge, HStack, IconButton } from '@chakra-ui/react';
import { RepeatIcon } from '@chakra-ui/icons';
import type { RoutePreset } from '../../types/zzpTrips';

interface RoutePresetCardsProps {
  presets: RoutePreset[];
  onSelect: (preset: RoutePreset, reversed: boolean) => void;
  selectedId?: number | null;
}

/**
 * Touch-friendly horizontal scroll for route presets.
 * Each card has a swap button (🔄) to reverse the direction.
 * Tapping the card fills the form; tapping swap flips from/to.
 */
export const RoutePresetCards: React.FC<RoutePresetCardsProps> = ({
  presets,
  onSelect,
  selectedId,
}) => {
  // Track which presets are currently shown in reversed direction
  const [reversedIds, setReversedIds] = useState<Set<number>>(new Set());

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

  const toggleReverse = (e: React.MouseEvent, presetId: number) => {
    e.stopPropagation(); // Don't trigger card selection
    setReversedIds((prev) => {
      const next = new Set(prev);
      if (next.has(presetId)) {
        next.delete(presetId);
      } else {
        next.add(presetId);
      }
      return next;
    });
  };

  return (
    <Flex
      overflowX="auto"
      gap={3}
      pb={2}
      css={{
        '&::-webkit-scrollbar': { height: '4px' },
        '&::-webkit-scrollbar-thumb': { background: '#4A5568', borderRadius: '4px' },
      }}
    >
      {presets.map((preset) => {
        const isReversed = reversedIds.has(preset.id);
        const fromAddr = isReversed ? preset.to_address : preset.from_address;
        const toAddr = isReversed ? preset.from_address : preset.to_address;

        return (
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
            onClick={() => onSelect(preset, isReversed)}
            minW="170px"
            minH="44px"
            display="flex"
            flexDirection="column"
            justifyContent="center"
            flexShrink={0}
            transition="all 0.15s ease"
            role="button"
            tabIndex={0}
            aria-label={`Route: ${fromAddr} naar ${toAddr}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(preset, isReversed);
              }
            }}
          >
            <Flex justify="space-between" align="flex-start">
              <Box flex={1} minW={0}>
                <Text fontSize="sm" fontWeight="medium" color="white" noOfLines={1}>
                  {fromAddr}
                </Text>
                <Text fontSize="sm" color="orange.200" mt={0.5} noOfLines={1}>
                  → {toAddr}
                </Text>
              </Box>
              <IconButton
                aria-label="Wissel richting"
                icon={<RepeatIcon boxSize={5} />}
                size="sm"
                variant="ghost"
                color="gray.400"
                _hover={{ color: 'orange.300', bg: 'gray.600' }}
                onClick={(e) => toggleReverse(e, preset.id)}
                ml={1}
                minW="36px"
                h="36px"
              />
            </Flex>
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
        );
      })}
    </Flex>
  );
};

export default RoutePresetCards;
