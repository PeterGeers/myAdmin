/**
 * ThemeSelector — Visual theme preset cards with colour swatches and font preview.
 *
 * Displays a grid of theme cards (from THEME_PRESETS) plus a "Custom" card.
 * Selecting a theme fills colour/font fields in the parent form.
 * A "Reset to theme defaults" button restores preset values (clears overrides).
 *
 * Tasks 35, 38, 39
 */

import React from 'react';
import {
  Box, Wrap, WrapItem, Text, Button, VStack, HStack,
} from '@chakra-ui/react';
import { THEME_PRESETS, ThemePreset } from './themePresets';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

// ============================================================================
// Types
// ============================================================================

export interface ThemeSelectorProps {
  selectedPreset: string | null;
  onSelectTheme: (presetId: string | null) => void;
  onReset: () => void;
}

// ============================================================================
// Component
// ============================================================================

export default function ThemeSelector({
  selectedPreset,
  onSelectTheme,
  onReset,
}: ThemeSelectorProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <VStack spacing={4} align="stretch">
      <Text color="white" fontWeight="bold" fontSize="sm">
        {t('landingPage.branding.chooseTheme')}
      </Text>

      <Wrap spacing={3}>
        {THEME_PRESETS.map((preset) => (
          <WrapItem key={preset.id}>
            <ThemeCard
              preset={preset}
              isSelected={selectedPreset === preset.id}
              onSelect={() => onSelectTheme(preset.id)}
            />
          </WrapItem>
        ))}

        {/* Custom card — Task 38 */}
        <WrapItem>
          <CustomCard
            isSelected={selectedPreset === null}
            onSelect={() => onSelectTheme(null)}
          />
        </WrapItem>
      </Wrap>

      {/* Reset to theme defaults — Task 39 */}
      {selectedPreset !== null && (
        <Box>
          <Button
            size="sm"
            variant="outline"
            colorScheme="orange"
            onClick={onReset}
          >
            {t('landingPage.branding.resetToDefaults')}
          </Button>
        </Box>
      )}
    </VStack>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

interface ThemeCardProps {
  preset: ThemePreset;
  isSelected: boolean;
  onSelect: () => void;
}

function ThemeCard({ preset, isSelected, onSelect }: ThemeCardProps) {
  return (
    <Box
      as="button"
      onClick={onSelect}
      bg="gray.700"
      borderRadius="md"
      p={3}
      w="110px"
      textAlign="center"
      cursor="pointer"
      border="2px solid"
      borderColor={isSelected ? 'orange.400' : 'gray.600'}
      _hover={{ borderColor: isSelected ? 'orange.400' : 'gray.400' }}
      transition="border-color 0.2s"
    >
      {/* Colour swatches */}
      <HStack spacing={1} justify="center" mb={2}>
        <Box
          w="20px"
          h="20px"
          borderRadius="sm"
          bg={preset.color_primary}
          border="1px solid"
          borderColor="gray.500"
        />
        <Box
          w="20px"
          h="20px"
          borderRadius="sm"
          bg={preset.color_accent}
          border="1px solid"
          borderColor="gray.500"
        />
        <Box
          w="20px"
          h="20px"
          borderRadius="sm"
          bg={preset.section_bg}
          border="1px solid"
          borderColor="gray.500"
        />
      </HStack>

      {/* Theme name */}
      <Text color="gray.200" fontSize="xs" fontWeight="medium" noOfLines={1}>
        {preset.name}
      </Text>

      {/* Font preview */}
      <Text color="gray.400" fontSize="2xs" noOfLines={1} mt={0.5}>
        {preset.font_heading === preset.font_body
          ? preset.font_heading
          : `${preset.font_heading} / ${preset.font_body}`}
      </Text>
    </Box>
  );
}

interface CustomCardProps {
  isSelected: boolean;
  onSelect: () => void;
}

function CustomCard({ isSelected, onSelect }: CustomCardProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <Box
      as="button"
      onClick={onSelect}
      bg="gray.700"
      borderRadius="md"
      p={3}
      w="110px"
      textAlign="center"
      cursor="pointer"
      border="2px solid"
      borderColor={isSelected ? 'orange.400' : 'gray.600'}
      _hover={{ borderColor: isSelected ? 'orange.400' : 'gray.400' }}
      transition="border-color 0.2s"
    >
      {/* Pencil icon area */}
      <Box h="20px" display="flex" alignItems="center" justifyContent="center" mb={2}>
        <Text fontSize="lg" color="gray.300">✎</Text>
      </Box>

      {/* Label */}
      <Text color="gray.200" fontSize="xs" fontWeight="medium">
        {t('landingPage.branding.customTheme')}
      </Text>

      <Text color="gray.400" fontSize="2xs" mt={0.5}>
        {t('landingPage.branding.manualControl')}
      </Text>
    </Box>
  );
}
