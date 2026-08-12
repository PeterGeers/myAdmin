/**
 * BlockConfigurator — Per-block settings panel.
 *
 * Renders form fields based on the block type and includes
 * the layout variant selector (Task 2.10).
 * Provides Content/Settings tabs (Task 10).
 */

import React from 'react';
import {
  Box, VStack, HStack, Text, Select, FormControl, FormLabel,
  Input, Textarea, CloseButton, Divider, FormHelperText,
  Tabs, TabList, Tab, TabPanels, TabPanel,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { Section, BlockSettings } from '../../../services/landingPageApi';
import { getLayoutsForType } from './blockTypeDefinitions';
import { DEFAULT_BLOCK_SETTINGS } from './blockSettingsDefaults';
import ImageUploader from './ImageUploader';
import FaqItemEditor from './FaqItemEditor';
import TestimonialsItemEditor from './TestimonialsItemEditor';
import GalleryItemEditor from './GalleryItemEditor';
import PricingItemEditor from './PricingItemEditor';
import BlockSettingsTab from './BlockSettingsTab';

interface BlockConfiguratorProps {
  section: Section;
  onUpdate: (updates: Partial<Section>) => void;
  onClose: () => void;
}

export default function BlockConfigurator({ section, onUpdate, onClose }: BlockConfiguratorProps) {
  const { t } = useTypedTranslation('admin');
  const layouts = getLayoutsForType(section.type);

  const updateProperty = (key: string, value: unknown) => {
    onUpdate({
      properties: { ...section.properties, [key]: value },
    });
  };

  const handleLayoutChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdate({ layout: e.target.value });
  };

  const currentSettings: BlockSettings = section.settings ?? DEFAULT_BLOCK_SETTINGS;

  const handleSettingsChange = (settings: BlockSettings) => {
    onUpdate({ settings });
  };

  return (
    <Box bg="gray.800" borderRadius="md" p={4} border="1px solid" borderColor="gray.600">
      {/* Header */}
      <HStack justify="space-between" mb={3}>
        <Text color="white" fontWeight="bold" fontSize="sm">
          {t(`landingPage.blockTypes.${section.type}`)} — {t('landingPage.editor.settings')}
        </Text>
        <CloseButton size="sm" color="gray.400" onClick={onClose} />
      </HStack>

      {/* Help text (Task 4.13) */}
      <Text color="gray.400" fontSize="xs" mb={3}>
        {t(`landingPage.blockHelp.${section.type}`)}
      </Text>

      {/* Tab switcher: Content / Settings */}
      <Tabs variant="soft-rounded" colorScheme="blue" size="sm">
        <TabList mb={3}>
          <Tab color="gray.400" _selected={{ color: 'white', bg: 'blue.600' }} fontSize="xs">
            {t('landingPage.editor.tabContent')}
          </Tab>
          <Tab color="gray.400" _selected={{ color: 'white', bg: 'blue.600' }} fontSize="xs">
            {t('landingPage.editor.tabSettings')}
          </Tab>
        </TabList>

        <TabPanels>
          {/* Tab 1: Content — existing field renderers */}
          <TabPanel p={0}>
            <VStack spacing={3} align="stretch">
              {/* Layout variant selector (Task 2.10) */}
              {layouts.length > 1 && (
                <FormControl>
                  <FormLabel color="gray.300" fontSize="xs" mb={1}>
                    {t('landingPage.editor.layout')}
                  </FormLabel>
                  <Select
                    size="sm"
                    bg="gray.700"
                    color="white"
                    borderColor="gray.600"
                    value={section.layout}
                    onChange={handleLayoutChange}
                  >
                    {layouts.map((layout) => (
                      <option key={layout} value={layout}>
                        {t(`landingPage.layouts.${layout}`)}
                      </option>
                    ))}
                  </Select>
                </FormControl>
              )}

              <Divider borderColor="gray.600" />

              {/* Type-specific fields */}
              {renderFieldsForType(section, updateProperty, t)}
            </VStack>
          </TabPanel>

          {/* Tab 2: Settings — block visual settings */}
          <TabPanel p={0}>
            <BlockSettingsTab
              settings={currentSettings}
              onSettingsChange={handleSettingsChange}
            />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}

// --- Type-specific field renderers ---

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function renderFieldsForType(
  section: Section,
  updateProperty: (key: string, value: unknown) => void,
  t: any,
) {
  const props = section.properties;

  switch (section.type) {
    case 'hero':
      return (
        <>
          <FieldInput label={t('landingPage.fields.title')} value={props.title as string} onChange={(v) => updateProperty('title', v)} />
          <FieldInput label={t('landingPage.fields.subtitle')} value={props.subtitle as string} onChange={(v) => updateProperty('subtitle', v)} />
          <FieldInput label={t('landingPage.fields.ctaText')} value={props.cta_text as string} onChange={(v) => updateProperty('cta_text', v)} />
          <FieldInput label={t('landingPage.fields.ctaUrl')} value={props.cta_url as string} onChange={(v) => updateProperty('cta_url', v)} placeholder="https://..." />
          <ImageUploader
            label={t('landingPage.fields.imageKey')}
            currentImageKey={props.image_key as string}
            onUpload={(key) => updateProperty('image_key', key)}
          />
          <FieldInput label={t('landingPage.fields.videoUrl')} value={props.video_url as string} onChange={(v) => updateProperty('video_url', v)} placeholder="https://youtube.com/watch?v=..." />
        </>
      );

    case 'about':
      return (
        <>
          <FieldTextarea label={t('landingPage.fields.content')} value={props.content_md as string} onChange={(v) => updateProperty('content_md', v)} />
          <ImageUploader
            label={t('landingPage.fields.imageKey')}
            currentImageKey={props.image_key as string}
            onUpload={(key) => updateProperty('image_key', key)}
          />
        </>
      );

    case 'cta':
      return (
        <>
          <FieldInput label={t('landingPage.fields.title')} value={props.title as string} onChange={(v) => updateProperty('title', v)} />
          <FieldInput label={t('landingPage.fields.subtitle')} value={props.subtitle as string} onChange={(v) => updateProperty('subtitle', v)} />
          <FieldInput label={t('landingPage.fields.buttonText')} value={props.button_text as string} onChange={(v) => updateProperty('button_text', v)} />
          <FieldInput label={t('landingPage.fields.buttonUrl')} value={props.button_url as string} onChange={(v) => updateProperty('button_url', v)} placeholder="https://..." />
        </>
      );

    case 'embed':
      return (
        <>
          <FormControl>
            <FormLabel color="gray.300" fontSize="xs" mb={1}>{t('landingPage.fields.embedUrl')}</FormLabel>
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={(props.url as string) || ''}
              onChange={(e) => updateProperty('url', e.target.value)}
              placeholder="https://..."
              _placeholder={{ color: 'gray.500' }}
            />
            <FormHelperText color="gray.500" fontSize="xs">
              {t('landingPage.fieldHelp.embedUrl')}
            </FormHelperText>
          </FormControl>
          <FieldInput label={t('landingPage.fields.height')} value={props.height as string} onChange={(v) => updateProperty('height', v)} placeholder="500px" />
          <FieldInput label={t('landingPage.fields.title')} value={props.title as string} onChange={(v) => updateProperty('title', v)} />
        </>
      );

    case 'contact':
      return (
        <>
          <FieldInput label={t('landingPage.fields.title')} value={props.title as string} onChange={(v) => updateProperty('title', v)} />
          <FieldInput label={t('landingPage.fields.subtitle')} value={props.subtitle as string} onChange={(v) => updateProperty('subtitle', v)} />
        </>
      );

    case 'faq':
      return (
        <FaqItemEditor
          items={(props.items as Array<{ question: string; answer: string }>) || []}
          title={(props.title as string) || ''}
          onUpdate={(updates) => {
            if (updates.items !== undefined) updateProperty('items', updates.items);
            if (updates.title !== undefined) updateProperty('title', updates.title);
          }}
        />
      );

    case 'testimonials':
      return (
        <TestimonialsItemEditor
          items={(props.items as Array<{ quote: string; author: string; role?: string }>) || []}
          title={(props.title as string) || ''}
          onUpdate={(updates) => {
            if (updates.items !== undefined) updateProperty('items', updates.items);
            if (updates.title !== undefined) updateProperty('title', updates.title);
          }}
        />
      );

    case 'gallery':
      return (
        <GalleryItemEditor
          images={(props.images as Array<{ image_key: string; alt?: string }>) || []}
          title={(props.title as string) || ''}
          onUpdate={(updates) => {
            if (updates.images !== undefined) updateProperty('images', updates.images);
            if (updates.title !== undefined) updateProperty('title', updates.title);
          }}
        />
      );

    case 'pricing':
      return (
        <PricingItemEditor
          items={(props.items as Array<{ name: string; price: string; description: string; features?: string[] }>) || []}
          title={(props.title as string) || ''}
          onUpdate={(updates) => {
            if (updates.items !== undefined) updateProperty('items', updates.items);
            if (updates.title !== undefined) updateProperty('title', updates.title);
          }}
        />
      );

    case 'services':
      return (
        <Text color="gray.400" fontSize="xs" fontStyle="italic">
          {t('landingPage.editor.liveDataBlock')}
        </Text>
      );

    case 'video':
      return (
        <>
          <VideoUrlField
            label={t('landingPage.fields.videoUrl')}
            value={props.video_url as string}
            onChange={(v) => updateProperty('video_url', v)}
            warningText={t('landingPage.fieldHelp.videoUrlInvalid')}
          />
          <FieldInput label={t('landingPage.fields.title')} value={props.title as string} onChange={(v) => updateProperty('title', v)} />
          <FieldInput label={t('landingPage.fields.description')} value={props.description as string} onChange={(v) => updateProperty('description', v)} />
        </>
      );

    default:
      return null;
  }
}

// --- Reusable field components ---

interface FieldInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

function FieldInput({ label, value, onChange, placeholder }: FieldInputProps) {
  return (
    <FormControl>
      <FormLabel color="gray.300" fontSize="xs" mb={1}>{label}</FormLabel>
      <Input
        size="sm"
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        _placeholder={{ color: 'gray.500' }}
      />
    </FormControl>
  );
}

interface FieldTextareaProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
}

function FieldTextarea({ label, value, onChange }: FieldTextareaProps) {
  return (
    <FormControl>
      <FormLabel color="gray.300" fontSize="xs" mb={1}>{label}</FormLabel>
      <Textarea
        size="sm"
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        _placeholder={{ color: 'gray.500' }}
      />
    </FormControl>
  );
}

// --- YouTube URL validation ---

const YOUTUBE_URL_REGEX = /(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/;

function isValidYouTubeUrl(url: string): boolean {
  if (!url) return true; // empty is valid (not required)
  return YOUTUBE_URL_REGEX.test(url);
}

interface VideoUrlFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  warningText: string;
}

function VideoUrlField({ label, value, onChange, warningText }: VideoUrlFieldProps) {
  const showWarning = !!value && !isValidYouTubeUrl(value);

  return (
    <FormControl>
      <FormLabel color="gray.300" fontSize="xs" mb={1}>{label}</FormLabel>
      <Input
        size="sm"
        bg="gray.700"
        color="white"
        borderColor={showWarning ? 'red.400' : 'gray.600'}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="https://youtube.com/watch?v=..."
        _placeholder={{ color: 'gray.500' }}
      />
      {showWarning && (
        <Text color="red.400" fontSize="xs" mt={1}>
          {warningText}
        </Text>
      )}
    </FormControl>
  );
}
