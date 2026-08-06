import React, { useEffect, useState } from 'react';
import { Box, Spinner, Center } from '@chakra-ui/react';
import { PublicThemeProvider } from './PublicThemeProvider';
import { PublicLayout } from './PublicLayout';
import {
  HeroBlock,
  AboutBlock,
  GalleryBlock,
  TestimonialsBlock,
  FaqBlock,
  PricingBlock,
  CtaBlock,
  EmbedBlock,
  ContactBlock,
  ServicesBlock,
} from './blocks';
import NotFoundPage from './NotFoundPage';

// ---------- Types ----------

interface LandingPageData {
  tenant_slug: string;
  published_at: string;
  version: number;
  branding: {
    name: string;
    tagline: string;
    logo_url: string;
    color_primary: string;
    color_accent: string;
  };
  footer: {
    company_name: string;
    address: string;
    postal_city: string;
    country: string;
    phone: string;
    email: string;
    coc: string;
    vat: string;
    social_links: Record<string, string>;
  };
  seo: {
    title: string;
    description: string;
    og_image: string;
    canonical_url: string;
  };
  settings: {
    show_share_buttons: boolean;
  };
  sections: Array<{
    id: string;
    type: string;
    layout: string;
    properties: Record<string, unknown>;
  }>;
}

type FetchState =
  | { status: 'loading' }
  | { status: 'success'; data: LandingPageData }
  | { status: 'not_found' }
  | { status: 'error'; message: string };

// ---------- Helpers ----------

function getCloudFrontBaseUrl(): string {
  const envUrl = import.meta.env.VITE_CLOUDFRONT_PUBLIC_PAGES_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  // Fallback: use current origin (dev/local)
  return window.location.origin;
}

function getTenantSlugFromPath(): string | null {
  // Strip base path (/myAdmin) if present
  const basePath = import.meta.env.BASE_URL?.replace(/\/$/, '') || '';
  const pathname = window.location.pathname;
  const path = pathname.startsWith(basePath)
    ? pathname.slice(basePath.length)
    : pathname;

  // Match /p/:tenantSlug
  const match = path.match(/^\/p\/([a-z0-9-]+)\/?$/);
  return match ? match[1] : null;
}

// ---------- Block Dispatcher ----------

interface BlockDispatcherProps {
  section: {
    id: string;
    type: string;
    layout: string;
    properties: Record<string, unknown>;
  };
  cloudFrontUrl: string;
  tenantSlug: string;
}

function BlockDispatcher({ section, cloudFrontUrl, tenantSlug }: BlockDispatcherProps) {
  const baseUrl = `${cloudFrontUrl}/${tenantSlug}`;

  switch (section.type) {
    case 'hero':
      return (
        <HeroBlock
          properties={section.properties as HeroBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'about':
      return (
        <AboutBlock
          properties={section.properties as AboutBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'gallery':
      return (
        <GalleryBlock
          properties={section.properties as GalleryBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'testimonials':
      return (
        <TestimonialsBlock
          properties={section.properties as TestimonialsBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'faq':
      return (
        <FaqBlock
          properties={section.properties as FaqBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'pricing':
      return (
        <PricingBlock
          properties={section.properties as PricingBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'cta':
      return (
        <CtaBlock
          properties={section.properties as CtaBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'embed':
      return (
        <EmbedBlock
          properties={section.properties as EmbedBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    case 'contact':
      return (
        <ContactBlock
          properties={section.properties as ContactBlockProps['properties']}
          layout={section.layout}
          tenantSlug={tenantSlug}
        />
      );
    case 'services':
      return (
        <ServicesBlock
          properties={section.properties as ServicesBlockProps['properties']}
          layout={section.layout}
          cloudFrontUrl={baseUrl}
        />
      );
    default:
      // Unknown block types are skipped gracefully
      return null;
  }
}

// Import types for casting
import type { HeroBlockProps } from './blocks/HeroBlock';
import type { AboutBlockProps } from './blocks/AboutBlock';
import type { GalleryBlockProps } from './blocks/GalleryBlock';
import type { TestimonialsBlockProps } from './blocks/TestimonialsBlock';
import type { FaqBlockProps } from './blocks/FaqBlock';
import type { PricingBlockProps } from './blocks/PricingBlock';
import type { CtaBlockProps } from './blocks/CtaBlock';
import type { EmbedBlockProps } from './blocks/EmbedBlock';
import type { ContactBlockProps } from './blocks/ContactBlock';
import type { ServicesBlockProps } from './blocks/ServicesBlock';

// ---------- Main Component ----------

/**
 * Public Landing Page
 *
 * Fetches the published landing.json from CloudFront/S3 and renders the
 * tenant's public landing page. No authentication required.
 *
 * Route: /p/:tenantSlug
 */
const PublicLandingPage: React.FC = () => {
  const [fetchState, setFetchState] = useState<FetchState>({ status: 'loading' });

  const tenantSlug = getTenantSlugFromPath();
  const cloudFrontUrl = getCloudFrontBaseUrl();

  useEffect(() => {
    if (!tenantSlug) {
      setFetchState({ status: 'not_found' });
      return;
    }

    let cancelled = false;

    async function fetchLandingData() {
      try {
        const url = `${cloudFrontUrl}/${tenantSlug}/landing.json`;
        const response = await fetch(url);

        if (cancelled) return;

        if (response.status === 404 || response.status === 403) {
          setFetchState({ status: 'not_found' });
          return;
        }

        if (!response.ok) {
          setFetchState({
            status: 'error',
            message: `Failed to load page (${response.status})`,
          });
          return;
        }

        const data: LandingPageData = await response.json();

        if (cancelled) return;
        setFetchState({ status: 'success', data });
      } catch {
        if (cancelled) return;
        setFetchState({ status: 'error', message: 'Failed to load page' });
      }
    }

    fetchLandingData();

    return () => {
      cancelled = true;
    };
  }, [tenantSlug, cloudFrontUrl]);

  // Loading state
  if (fetchState.status === 'loading') {
    return (
      <Center minH="100vh" bg="white">
        <Spinner size="xl" color="orange.400" thickness="4px" />
      </Center>
    );
  }

  // 404 / not found state
  if (fetchState.status === 'not_found') {
    return <NotFoundPage />;
  }

  // Error state — show not found for simplicity (no user-facing error details)
  if (fetchState.status === 'error') {
    return <NotFoundPage />;
  }

  // Success — render the landing page
  const { data } = fetchState;

  return (
    <PublicThemeProvider branding={data.branding}>
      <PublicLayout
        branding={data.branding}
        footer={data.footer}
        seo={data.seo}
        settings={data.settings}
      >
        {data.sections.map((section) => (
          <Box key={section.id}>
            <BlockDispatcher
              section={section}
              cloudFrontUrl={cloudFrontUrl}
              tenantSlug={data.tenant_slug}
            />
          </Box>
        ))}
      </PublicLayout>
    </PublicThemeProvider>
  );
};

export default PublicLandingPage;
