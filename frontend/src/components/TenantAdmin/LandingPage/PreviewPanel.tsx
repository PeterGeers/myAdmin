/**
 * PreviewPanel — Renders the current draft sections as if published.
 *
 * Uses the same block renderers as the public landing page to give
 * an accurate preview within the admin editor.
 *
 * Task 2.21
 */

import React from 'react';
import { Box, Badge, Image, Text } from '@chakra-ui/react';
import {
  HeroBlock,
  AboutBlock,
  GalleryBlock,
  TestimonialsBlock,
  FaqBlock,
  PricingBlock,
  CtaBlock,
  EmbedBlock,
} from '../../../pages/public/blocks';
import type { HeroBlockProps } from '../../../pages/public/blocks/HeroBlock';
import type { AboutBlockProps } from '../../../pages/public/blocks/AboutBlock';
import type { GalleryBlockProps } from '../../../pages/public/blocks/GalleryBlock';
import type { TestimonialsBlockProps } from '../../../pages/public/blocks/TestimonialsBlock';
import type { FaqBlockProps } from '../../../pages/public/blocks/FaqBlock';
import type { PricingBlockProps } from '../../../pages/public/blocks/PricingBlock';
import type { CtaBlockProps } from '../../../pages/public/blocks/CtaBlock';
import type { EmbedBlockProps } from '../../../pages/public/blocks/EmbedBlock';
import type { Section, BlockSettings } from '../../../services/landingPageApi';
import { DEFAULT_BLOCK_SETTINGS } from './blockSettingsDefaults';

// ---------- Types ----------

interface PreviewPanelProps {
  sections: Section[];
  branding?: {
    color_primary: string;
    color_accent: string;
    name: string;
    tagline: string;
    logo_url: string;
  };
}

// ---------- Helpers ----------

const PADDING_MAP: Record<BlockSettings['padding'], string> = {
  compact: '0.5rem 1rem',
  normal: '1rem 1.5rem',
  spacious: '2rem 1.5rem',
};

const TEXT_COLOR_MAP: Record<BlockSettings['text_color'], string> = {
  dark: '#333',
  light: '#fff',
  auto: 'inherit',
};

const BORDER_RADIUS_MAP: Record<BlockSettings['border_radius'], string> = {
  none: '0',
  sm: '8px',
  md: '16px',
  lg: '24px',
};

/**
 * Convert BlockSettings into React inline styles for the section wrapper.
 * Returns an empty object when settings are absent (backwards compatible).
 */
function buildSectionStyle(
  settings: BlockSettings | undefined,
  cloudFrontUrl: string,
): React.CSSProperties {
  if (!settings) return {};

  const style: React.CSSProperties = {};

  // Background
  switch (settings.background_type) {
    case 'color':
      if (settings.background_color && settings.background_color !== 'transparent') {
        style.backgroundColor = settings.background_color;
      }
      break;
    case 'gradient':
      if (settings.background_gradient) {
        style.background = settings.background_gradient;
      }
      break;
    case 'image':
      if (settings.background_image_key) {
        const url = `${cloudFrontUrl}/${settings.background_image_key}`;
        style.backgroundImage = `url(${url})`;
        style.backgroundSize = 'cover';
        style.backgroundPosition = 'center';
      }
      break;
  }

  // Padding
  style.padding = PADDING_MAP[settings.padding] ?? PADDING_MAP[DEFAULT_BLOCK_SETTINGS.padding];

  // Text colour
  style.color = TEXT_COLOR_MAP[settings.text_color] ?? TEXT_COLOR_MAP[DEFAULT_BLOCK_SETTINGS.text_color];

  // Max width
  if (settings.max_width === 'contained') {
    style.maxWidth = '1200px';
    style.marginLeft = 'auto';
    style.marginRight = 'auto';
  }

  // Border radius
  const radius = BORDER_RADIUS_MAP[settings.border_radius] ?? BORDER_RADIUS_MAP[DEFAULT_BLOCK_SETTINGS.border_radius];
  if (radius !== '0') {
    style.borderRadius = radius;
  }

  return style;
}

/**
 * Get the CloudFront base URL for images.
 * Since image_key in the draft already includes the slug prefix
 * (e.g. "my-slug/images/abc.jpg"), we use the raw CloudFront domain
 * as the base so that `${cloudFrontUrl}/${image_key}` resolves correctly.
 */
function getCloudFrontBaseUrl(): string {
  const domain = import.meta.env.VITE_CLOUDFRONT_DOMAIN;
  if (domain) return `https://${domain}`;
  const envUrl = import.meta.env.VITE_CLOUDFRONT_PUBLIC_PAGES_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  return '';
}

// ---------- Block Dispatcher ----------

interface PreviewBlockDispatcherProps {
  section: Section;
  cloudFrontUrl: string;
}

function PreviewBlockDispatcher({ section, cloudFrontUrl }: PreviewBlockDispatcherProps) {
  switch (section.type) {
    case 'hero':
      return (
        <HeroBlock
          properties={section.properties as HeroBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'about':
      return (
        <AboutBlock
          properties={section.properties as AboutBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'gallery':
      return (
        <GalleryBlock
          properties={section.properties as GalleryBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'testimonials':
      return (
        <TestimonialsBlock
          properties={section.properties as TestimonialsBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'faq':
      return (
        <FaqBlock
          properties={section.properties as FaqBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'pricing':
      return (
        <PricingBlock
          properties={section.properties as PricingBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'cta':
      return (
        <CtaBlock
          properties={section.properties as CtaBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'embed':
      return (
        <EmbedBlock
          properties={section.properties as EmbedBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={cloudFrontUrl}
        />
      );
    case 'video': {
      const videoUrl = section.properties.video_url as string || '';
      const videoId = videoUrl.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/)?.[1] || '';
      const videoTitle = section.properties.title as string || '';
      const videoDesc = section.properties.description as string || '';
      const isCentered = section.layout !== 'full-width';

      return (
        <Box maxW={isCentered ? '800px' : '100%'} mx="auto" px={4} py={6}>
          {videoTitle && <Text fontWeight="bold" fontSize="lg" mb={2}>{videoTitle}</Text>}
          {videoId ? (
            <Box position="relative" paddingBottom="56.25%" bg="gray.900" borderRadius="md" overflow="hidden">
              <Image
                src={`https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`}
                alt={videoTitle || 'Video thumbnail'}
                position="absolute"
                top={0} left={0} w="100%" h="100%"
                objectFit="cover"
              />
              <Box position="absolute" top="50%" left="50%" transform="translate(-50%, -50%)"
                w="68px" h="48px" bg="blackAlpha.700" borderRadius="md"
                display="flex" alignItems="center" justifyContent="center">
                <Box as="span" w={0} h={0} borderStyle="solid" borderWidth="10px 0 10px 18px"
                  borderColor="transparent transparent transparent white" />
              </Box>
            </Box>
          ) : (
            <Box bg="gray.200" borderRadius="md" h="200px" display="flex" alignItems="center" justifyContent="center">
              <Text color="gray.500">Enter a YouTube URL to preview</Text>
            </Box>
          )}
          {videoDesc && <Text color="gray.600" fontSize="sm" mt={2}>{videoDesc}</Text>}
        </Box>
      );
    }
    default:
      return null;
  }
}

// ---------- Main Component ----------

const PreviewPanel: React.FC<PreviewPanelProps> = ({ sections, branding }) => {
  const cloudFrontUrl = getCloudFrontBaseUrl();

  if (sections.length === 0) {
    return (
      <Box
        p={8}
        textAlign="center"
        bg="gray.100"
        borderRadius="md"
        border="1px solid"
        borderColor="gray.300"
      >
        <Text color="gray.500">No blocks to preview. Add some blocks first.</Text>
      </Box>
    );
  }

  return (
    <Box>
      {/* Preview badge */}
      <Badge
        colorScheme="purple"
        fontSize="xs"
        mb={3}
        px={2}
        py={1}
        borderRadius="sm"
      >
        👁 Preview
      </Badge>

      {/* Preview container — light background to simulate public page */}
      <Box
        bg="white"
        color="gray.800"
        border="1px solid"
        borderColor="gray.300"
        borderRadius="md"
        overflow="hidden"
        maxH="70vh"
        overflowY="auto"
        sx={{
          // Apply branding colors as CSS variables for blocks that use them
          '--color-primary': branding?.color_primary || '#DD6B20',
          '--color-accent': branding?.color_accent || '#ED8936',
        }}
      >
        {sections.map((section) => {
          const sectionStyle = buildSectionStyle(section.settings, cloudFrontUrl);
          return (
            <Box key={section.id} style={sectionStyle}>
              <PreviewBlockDispatcher
                section={section}
                cloudFrontUrl={cloudFrontUrl}
              />
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

export default PreviewPanel;
