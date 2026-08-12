/**
 * BlockSettingsTab — Per-block visual settings panel.
 *
 * Renders controls for background, padding, text colour, max-width,
 * and border-radius. Shown in the "Settings" tab of BlockConfigurator.
 */

import React from 'react';
import {
  VStack, FormControl, FormLabel, RadioGroup, Radio, Stack,
  Button, ButtonGroup, Input, Text, HStack,
} from '@chakra-ui/react';
import { BlockSettings } from '@/services/landingPageApi';
import { DEFAULT_BLOCK_SETTINGS } from './blockSettingsDefaults';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import ImageUploader from './ImageUploader';
import GradientPicker from './GradientPicker';

interface BlockSettingsTabProps {
  settings: BlockSettings;
  onSettingsChange: (settings: BlockSettings) => void;
}

export default function BlockSettingsTab({ settings, onSettingsChange }: BlockSettingsTabProps) {
  const { t } = useTypedTranslation('admin');

  const update = <K extends keyof BlockSettings>(key: K, value: BlockSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value });
  };

  return (
    <VStack spacing={4} align="stretch">
      {/* 1. Background type selector */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.settings.backgroundType')}
        </FormLabel>
        <RadioGroup
          value={settings.background_type}
          onChange={(val) => update('background_type', val as BlockSettings['background_type'])}
        >
          <Stack direction="row" spacing={4}>
            <Radio value="color" colorScheme="blue" size="sm">
              <Text color="gray.300" fontSize="xs">{t('landingPage.settings.bgColour')}</Text>
            </Radio>
            <Radio value="image" colorScheme="blue" size="sm">
              <Text color="gray.300" fontSize="xs">{t('landingPage.settings.bgImage')}</Text>
            </Radio>
            <Radio value="gradient" colorScheme="blue" size="sm">
              <Text color="gray.300" fontSize="xs">{t('landingPage.settings.bgGradient')}</Text>
            </Radio>
          </Stack>
        </RadioGroup>
      </FormControl>

      {/* 2. Colour picker — shown when background_type === "color" */}
      {settings.background_type === 'color' && (
        <FormControl>
          <FormLabel color="gray.300" fontSize="xs" mb={1}>
            {t('landingPage.settings.backgroundColor')}
          </FormLabel>
          <HStack>
            <Input
              type="color"
              size="sm"
              w="50px"
              h="32px"
              p={0}
              border="none"
              cursor="pointer"
              value={settings.background_color === 'transparent' ? '#ffffff' : settings.background_color}
              onChange={(e) => update('background_color', e.target.value)}
            />
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              w="120px"
              value={settings.background_color}
              onChange={(e) => update('background_color', e.target.value)}
              placeholder="#f9f9f9"
              _placeholder={{ color: 'gray.500' }}
            />
          </HStack>
        </FormControl>
      )}

      {/* 3. Image uploader — shown when background_type === "image" */}
      {settings.background_type === 'image' && (
        <FormControl>
          <FormLabel color="gray.300" fontSize="xs" mb={1}>
            {t('landingPage.settings.backgroundImage')}
          </FormLabel>
          <ImageUploader
            onUpload={(key) => update('background_image_key', key)}
            currentImageKey={settings.background_image_key || undefined}
            label={t('landingPage.settings.backgroundImage')}
          />
        </FormControl>
      )}

      {/* 4. Gradient picker — shown when background_type === "gradient" */}
      {settings.background_type === 'gradient' && (
        <FormControl>
          <FormLabel color="gray.300" fontSize="xs" mb={1}>
            {t('landingPage.settings.backgroundGradient')}
          </FormLabel>
          <GradientPicker
            value={settings.background_gradient}
            onChange={(gradient) => update('background_gradient', gradient)}
          />
        </FormControl>
      )}

      {/* 5. Padding selector */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.settings.padding')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {(['compact', 'normal', 'spacious'] as const).map((val) => (
            <Button
              key={val}
              flex={1}
              colorScheme={settings.padding === val ? 'blue' : undefined}
              variant={settings.padding === val ? 'solid' : 'outline'}
              borderColor="gray.600"
              color={settings.padding === val ? 'white' : 'gray.300'}
              onClick={() => update('padding', val)}
            >
              {t(`landingPage.settings.padding_${val}`)}
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>

      {/* 6. Text colour selector */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.settings.textColour')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {(['dark', 'light', 'auto'] as const).map((val) => (
            <Button
              key={val}
              flex={1}
              colorScheme={settings.text_color === val ? 'blue' : undefined}
              variant={settings.text_color === val ? 'solid' : 'outline'}
              borderColor="gray.600"
              color={settings.text_color === val ? 'white' : 'gray.300'}
              onClick={() => update('text_color', val)}
            >
              {t(`landingPage.settings.textColor_${val}`)}
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>

      {/* 7. Max-width toggle */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.settings.maxWidth')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {(['contained', 'full-width'] as const).map((val) => (
            <Button
              key={val}
              flex={1}
              colorScheme={settings.max_width === val ? 'blue' : undefined}
              variant={settings.max_width === val ? 'solid' : 'outline'}
              borderColor="gray.600"
              color={settings.max_width === val ? 'white' : 'gray.300'}
              onClick={() => update('max_width', val)}
            >
              {t(`landingPage.settings.maxWidth_${val}`)}
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>

      {/* 8. Border-radius selector */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.settings.borderRadius')}
        </FormLabel>
        <ButtonGroup size="sm" isAttached variant="outline" w="100%">
          {(['none', 'sm', 'md', 'lg'] as const).map((val) => (
            <Button
              key={val}
              flex={1}
              colorScheme={settings.border_radius === val ? 'blue' : undefined}
              variant={settings.border_radius === val ? 'solid' : 'outline'}
              borderColor="gray.600"
              color={settings.border_radius === val ? 'white' : 'gray.300'}
              onClick={() => update('border_radius', val)}
            >
              {t(`landingPage.settings.borderRadius_${val}`)}
            </Button>
          ))}
        </ButtonGroup>
      </FormControl>
    </VStack>
  );
}
