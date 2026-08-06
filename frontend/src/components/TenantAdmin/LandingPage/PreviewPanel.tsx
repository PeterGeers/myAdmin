/**
 * PreviewPanel — Renders the current draft sections as if published.
 *
 * Uses the same block renderers as the public landing page to give
 * an accurate preview within the admin editor.
 *
 * Task 2.21
 */

import React from 'react';
import { Box, Badge, Text } from '@chakra-ui/react';
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
import type { Section } from '../../../services/landingPageApi';

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
        {sections.map((section) => (
          <Box key={section.id}>
            <PreviewBlockDispatcher
              section={section}
              cloudFrontUrl={cloudFrontUrl}
            />
          </Box>
        ))}
      </Box>
    </Box>
  );
};

export default PreviewPanel;
