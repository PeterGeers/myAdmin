/**
 * TypographySettings — Font dropdowns, spacing, border-radius, and shadow selectors.
 *
 * Provides global typography & design token controls for the published landing page:
 * - Font heading dropdown with live preview
 * - Font body dropdown with live preview
 * - Spacing selector (compact / normal / relaxed)
 * - Border-radius selector (sharp / rounded / pill)
 * - Shadow selector (none / subtle / medium / dramatic)
 *
 * Task 52
 */

import React from 'react';
import {
  Box, VStack, HStack, Text, FormControl, FormLabel, Select,
  ButtonGroup, Button, SimpleGrid,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';

// ============================================================================
// Types & Constants
// ============================================================================

export interface TypographySettingsProps {
  fontHeading: string;
  fontBody: string;
  baseSpacing: string;
  borderRadiusGlobal: string;
  shadowStyle: string;
  onFontHeadingChange: (font: string) => void;
  onFontBodyChange: (font: string) => void;
  onSpacingChange: (spacing: string) => void;
  onRadiusChange: (radius: string) => void;
  onShadowChange: (shadow: string) => void;
}

interface FontOption {
  value: string;
  label: string;
  family: string; // CSS font-family for preview
}

const FONT_OPTIONS: FontOption[] = [
  { value: 'system', label: 'System Default', family: '-apple-system, BlinkMacSystemFont, sans-serif' },
  { value: 'Inter', label: 'Inter', family: '"Inter", sans-serif' },
  { value: 'Lora', label: 'Lora', family: '"Lora", serif' },
  { value: 'Poppins', label: 'Poppins', family: '"Poppins", sans-serif' },
  { value: 'Nunito', label: 'Nunito', family: '"Nunito", sans-serif' },
  { value: 'Playfair Display', label: 'Playfair Display', family: '"Playfair Display", serif' },
  { value: 'Lato', label: 'Lato', family: '"Lato", sans-serif' },
];

type SpacingOption = 'compact' | 'normal' | 'relaxed';
type RadiusOption = 'sharp' | 'rounded' | 'pill';
type ShadowOption = 'none' | 'subtle' | 'medium' | 'dramatic';

const SPACING_OPTIONS: SpacingOption[] = ['compact', 'normal', 'relaxed'];
const RADIUS_OPTIONS: RadiusOption[] = ['sharp', 'rounded', 'pill'];
const SHADOW_OPTIONS: ShadowOption[] = ['none', 'subtle', 'medium', 'dramatic'];

// Visual preview values for border-radius
const RADIUS_PREVIEW: Record<RadiusOption, string> = {
  sharp: '0px',
  rounded: '8px',
  pill: '9999px',
};

// Visual preview values for shadows
const SHADOW_PREVIEW: Record<ShadowOption, string> = {
  none: 'none',
  subtle: '0 2px 8px rgba(0,0,0,0.08)',
  medium: '0 4px 12px rgba(0,0,0,0.12)',
  dramatic: '0 8px 24px rgba(0,0,0,0.2)',
};

// ============================================================================
// Component
// ============================================================================

export default function TypographySettings({
  fontHeading,
  fontBody,
  baseSpacing,
  borderRadiusGlobal,
  shadowStyle,
  onFontHeadingChange,
  onFontBodyChange,
  onSpacingChange,
  onRadiusChange,
  onShadowChange,
}: TypographySettingsProps) {
  const { t } = useTypedTranslation('admin');

  const selectedHeadingFont = FONT_OPTIONS.find(f => f.value === fontHeading) || FONT_OPTIONS[0];
  const selectedBodyFont = FONT_OPTIONS.find(f => f.value === fontBody) || FONT_OPTIONS[0];

  return (
    <VStack spacing={5} align="stretch">
      <Text color="white" fontWeight="bold" fontSize="sm">
        {t('landingPage.branding.typography')}
      </Text>

      {/* Font Heading */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.branding.fontHeading')}
        </FormLabel>
        <Select
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={fontHeading || 'system'}
          onChange={(e) => onFontHeadingChange(e.target.value)}
        >
          {FONT_OPTIONS.map((font) => (
            <option key={font.value} value={font.value} style={{ fontFamily: font.family }}>
              {font.label}
            </option>
          ))}
        </Select>
        {/* Live preview text — heading font */}
        <Box mt={2} p={2} bg="gray.800" borderRadius="md">
          <Text
            fontSize="lg"
            fontWeight="bold"
            color="gray.100"
            fontFamily={selectedHeadingFont.family}
          >
            {t('landingPage.branding.fontPreviewHeading')}
          </Text>
        </Box>
      </FormControl>

      {/* Font Body */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.branding.fontBody')}
        </FormLabel>
        <Select
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={fontBody || 'system'}
          onChange={(e) => onFontBodyChange(e.target.value)}
        >
          {FONT_OPTIONS.map((font) => (
            <option key={font.value} value={font.value} style={{ fontFamily: font.family }}>
              {font.label}
            </option>
          ))}
        </Select>
        {/* Live preview text — body font */}
        <Box mt={2} p={2} bg="gray.800" borderRadius="md">
          <Text
            fontSize="sm"
            color="gray.300"
            fontFamily={selectedBodyFont.family}
          >
            {t('landingPage.branding.fontPreviewBody')}
          </Text>
        </Box>
      </FormControl>

      {/* Spacing selector — 3 visual buttons */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.branding.baseSpacing')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {SPACING_OPTIONS.map((option) => (
            <Button
              key={option}
              flex={1}
              onClick={() => onSpacingChange(option)}
              bg={baseSpacing === option ? 'orange.500' : 'gray.700'}
              color={baseSpacing === option ? 'white' : 'gray.300'}
              borderColor={baseSpacing === option ? 'orange.500' : 'gray.600'}
              _hover={{
                bg: baseSpacing === option ? 'orange.600' : 'gray.600',
              }}
            >
              {t(`landingPage.branding.spacing_${option}`)}
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>

      {/* Border-radius selector — 3 visual rectangles */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.branding.borderRadius')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {RADIUS_OPTIONS.map((option) => (
            <Button
              key={option}
              flex={1}
              onClick={() => onRadiusChange(option)}
              bg={borderRadiusGlobal === option ? 'orange.500' : 'gray.700'}
              color={borderRadiusGlobal === option ? 'white' : 'gray.300'}
              borderColor={borderRadiusGlobal === option ? 'orange.500' : 'gray.600'}
              _hover={{
                bg: borderRadiusGlobal === option ? 'orange.600' : 'gray.600',
              }}
            >
              <HStack spacing={2}>
                <Box
                  w="16px"
                  h="16px"
                  bg="gray.400"
                  borderRadius={RADIUS_PREVIEW[option]}
                />
                <Text fontSize="xs">
                  {t(`landingPage.branding.radius_${option}`)}
                </Text>
              </HStack>
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>

      {/* Shadow selector — 4 card previews */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.branding.shadowStyle')}
        </FormLabel>
        <SimpleGrid columns={4} spacing={2}>
          {SHADOW_OPTIONS.map((option) => (
            <Box
              key={option}
              as="button"
              type="button"
              onClick={() => onShadowChange(option)}
              p={3}
              bg={shadowStyle === option ? 'gray.600' : 'gray.700'}
              borderRadius="md"
              border="2px solid"
              borderColor={shadowStyle === option ? 'orange.400' : 'gray.600'}
              cursor="pointer"
              textAlign="center"
              transition="all 0.15s"
              _hover={{ borderColor: 'orange.300' }}
            >
              <Box
                w="100%"
                h="24px"
                bg="gray.300"
                borderRadius="4px"
                boxShadow={SHADOW_PREVIEW[option]}
                mx="auto"
                mb={1}
              />
              <Text fontSize="2xs" color={shadowStyle === option ? 'orange.200' : 'gray.400'}>
                {t(`landingPage.branding.shadow_${option}`)}
              </Text>
            </Box>
          ))}
        </SimpleGrid>
      </FormControl>
    </VStack>
  );
}
