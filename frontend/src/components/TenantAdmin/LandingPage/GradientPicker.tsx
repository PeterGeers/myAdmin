/**
 * GradientPicker — Preset gradient buttons + free-form CSS gradient input.
 *
 * Provides a visual way to select from curated gradient presets,
 * a free-form text input for custom CSS gradients, and a live preview strip.
 *
 * Task 14 — Landing Page Look & Feel spec.
 */

import React from 'react';
import {
  VStack, HStack, Input, Box, Text, Tooltip, Wrap, WrapItem,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

interface GradientPickerProps {
  value: string;
  onChange: (gradient: string) => void;
}

const GRADIENT_PRESETS = [
  { name: 'Sunset', value: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' },
  { name: 'Ocean', value: 'linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%)' },
  { name: 'Forest', value: 'linear-gradient(135deg, #134e5e 0%, #71b280 100%)' },
  { name: 'Peach', value: 'linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)' },
  { name: 'Night', value: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)' },
  { name: 'Warm', value: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' },
  { name: 'Sky', value: 'linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)' },
  { name: 'Gold', value: 'linear-gradient(135deg, #f7971e 0%, #ffd200 100%)' },
];

export default function GradientPicker({ value, onChange }: GradientPickerProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <VStack spacing={3} align="stretch">
      {/* Preset gradient buttons */}
      <Wrap spacing={2}>
        {GRADIENT_PRESETS.map((preset) => (
          <WrapItem key={preset.name}>
            <Tooltip label={preset.name} placement="top" hasArrow>
              <Box
                as="button"
                type="button"
                w="32px"
                h="32px"
                borderRadius="md"
                background={preset.value}
                border="2px solid"
                borderColor={value === preset.value ? 'blue.400' : 'gray.600'}
                cursor="pointer"
                transition="all 0.15s"
                _hover={{ borderColor: 'blue.300', transform: 'scale(1.1)' }}
                _focus={{ outline: 'none', boxShadow: '0 0 0 2px var(--chakra-colors-blue-400)' }}
                onClick={() => onChange(preset.value)}
                aria-label={`${preset.name} gradient preset`}
              />
            </Tooltip>
          </WrapItem>
        ))}
      </Wrap>

      {/* Free-form gradient input */}
      <Input
        size="sm"
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
        _placeholder={{ color: 'gray.500' }}
        aria-label={t('landingPage.settings.backgroundGradient')}
      />

      {/* Preview strip */}
      {value && (
        <Box
          h="24px"
          borderRadius="md"
          background={value}
          border="1px solid"
          borderColor="gray.600"
        />
      )}
    </VStack>
  );
}
