/**
 * SeoSettings — SEO title, description, and OG image upload with preview.
 *
 * Provides character counters, OG image upload guidance (1200×630px),
 * and a preview card showing how the page will appear when shared.
 *
 * Task 3.17
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Text, FormControl, FormLabel, Input, Textarea,
  Button, useToast, Spinner, Image, Badge,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  getBrandingSettings, saveBrandingSettings, LandingPageSettings,
} from '../../../services/landingPageApi';
import ImageUploader from './ImageUploader';

// ============================================================================
// Constants
// ============================================================================

const SEO_TITLE_MAX = 60;
const SEO_DESCRIPTION_MAX = 160;

// ============================================================================
// Component
// ============================================================================

export default function SeoSettings() {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [seoTitle, setSeoTitle] = useState('');
  const [seoDescription, setSeoDescription] = useState('');
  const [ogImageUrl, setOgImageUrl] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data: LandingPageSettings = await getBrandingSettings();
      setSeoTitle(data.seo_title || '');
      setSeoDescription(data.seo_description || '');
      setOgImageUrl(data.og_image_url || '');
    } catch {
      // Use defaults if no settings exist
    } finally {
      setLoading(false);
    }
  };

  const handleImageUpload = useCallback((imageKey: string) => {
    // Build the full URL from the image key
    const cloudfrontDomain = import.meta.env.VITE_CLOUDFRONT_DOMAIN || '';
    const url = imageKey ? `https://${cloudfrontDomain}/${imageKey}` : '';
    setOgImageUrl(url);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveBrandingSettings({
        seo_title: seoTitle,
        seo_description: seoDescription,
        og_image_url: ogImageUrl,
      });
      toast({
        title: t('landingPage.seo.saved'),
        status: 'success',
        duration: 3000,
      });
    } catch (err) {
      toast({
        title: t('landingPage.seo.saveError'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minH="200px">
        <Spinner size="lg" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      {/* SEO Title */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.seo.title')}
        </FormLabel>
        <Input
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={seoTitle}
          onChange={(e) => setSeoTitle(e.target.value)}
          placeholder={t('landingPage.seo.titlePlaceholder')}
          _placeholder={{ color: 'gray.500' }}
        />
        <CharacterCounter current={seoTitle.length} max={SEO_TITLE_MAX} />
      </FormControl>

      {/* SEO Description */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.seo.description')}
        </FormLabel>
        <Textarea
          size="sm"
          bg="gray.700"
          color="white"
          borderColor="gray.600"
          value={seoDescription}
          onChange={(e) => setSeoDescription(e.target.value)}
          placeholder={t('landingPage.seo.descriptionPlaceholder')}
          _placeholder={{ color: 'gray.500' }}
          rows={3}
        />
        <CharacterCounter current={seoDescription.length} max={SEO_DESCRIPTION_MAX} />
      </FormControl>

      {/* OG Image */}
      <FormControl>
        <FormLabel color="gray.300" fontSize="xs" mb={1}>
          {t('landingPage.seo.ogImage')}
        </FormLabel>
        <Text color="gray.400" fontSize="xs" mb={2}>
          {t('landingPage.seo.ogImageHelp')}
        </Text>
        <ImageUploader
          onUpload={handleImageUpload}
          currentImageKey={ogImageUrl ? extractImageKey(ogImageUrl) : undefined}
        />
      </FormControl>

      {/* OG Preview Card */}
      <Box>
        <Text color="white" fontWeight="bold" fontSize="sm" mb={2}>
          {t('landingPage.seo.preview')}
        </Text>
        <OgPreviewCard
          title={seoTitle}
          description={seoDescription}
          imageUrl={ogImageUrl}
        />
      </Box>

      {/* Save button */}
      <HStack justify="flex-end">
        <Button
          colorScheme="orange"
          size="sm"
          onClick={handleSave}
          isLoading={saving}
        >
          {t('landingPage.seo.save')}
        </Button>
      </HStack>
    </VStack>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

interface CharacterCounterProps {
  current: number;
  max: number;
}

function CharacterCounter({ current, max }: CharacterCounterProps) {
  const isOver = current > max;
  const color = isOver ? 'red.300' : current > max * 0.9 ? 'yellow.300' : 'gray.400';

  return (
    <HStack justify="flex-end" mt={1}>
      <Text fontSize="xs" color={color}>
        {current}/{max}
      </Text>
      {isOver && (
        <Badge colorScheme="red" fontSize="xs">
          over limit
        </Badge>
      )}
    </HStack>
  );
}

interface OgPreviewCardProps {
  title: string;
  description: string;
  imageUrl: string;
}

function OgPreviewCard({ title, description, imageUrl }: OgPreviewCardProps) {
  return (
    <Box
      border="1px solid"
      borderColor="gray.600"
      borderRadius="md"
      overflow="hidden"
      maxW="500px"
      bg="gray.800"
    >
      {/* Image preview */}
      <Box
        bg="gray.700"
        h="160px"
        display="flex"
        alignItems="center"
        justifyContent="center"
        overflow="hidden"
      >
        {imageUrl ? (
          <Image
            src={imageUrl}
            alt="OG preview"
            w="100%"
            h="100%"
            objectFit="cover"
            fallback={
              <Text color="gray.500" fontSize="xs">
                Image preview
              </Text>
            }
          />
        ) : (
          <VStack spacing={1}>
            <Text color="gray.500" fontSize="xs">
              1200 × 630 px
            </Text>
            <Text color="gray.600" fontSize="xs">
              No image uploaded
            </Text>
          </VStack>
        )}
      </Box>

      {/* Text preview */}
      <Box p={3}>
        <Text
          color="gray.400"
          fontSize="xs"
          textTransform="uppercase"
          mb={1}
        >
          myadmin.app
        </Text>
        <Text
          color="white"
          fontSize="sm"
          fontWeight="bold"
          noOfLines={2}
          mb={1}
        >
          {title || 'Page title'}
        </Text>
        <Text color="gray.300" fontSize="xs" noOfLines={2}>
          {description || 'Page description will appear here'}
        </Text>
      </Box>
    </Box>
  );
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Extracts the image key from a full CloudFront URL.
 * e.g., "https://cdn.example.com/tenant/images/og.jpg" → "tenant/images/og.jpg"
 */
function extractImageKey(url: string): string {
  if (!url) return '';
  try {
    const parsed = new URL(url);
    // Remove leading slash
    return parsed.pathname.replace(/^\//, '');
  } catch {
    return url;
  }
}
