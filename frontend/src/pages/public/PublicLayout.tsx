import React from 'react';
import { Box, Container, Flex, HStack, Image, Text } from '@chakra-ui/react';
import { SocialMetaTags } from './SocialMetaTags';
import { PublicFooter } from './PublicFooter';
import { ShareButtons } from './ShareButtons';

export interface SeoData {
  title: string;
  description: string;
  og_image: string;
  canonical_url: string;
}

export interface FooterData {
  company_name: string;
  address: string;
  postal_city: string;
  country: string;
  phone: string;
  email: string;
  coc: string;
  vat: string;
  social_links: Record<string, string>;
}

interface PublicLayoutProps {
  children: React.ReactNode;
  branding: {
    name: string;
    logo_url: string;
    tagline: string;
  };
  footer: FooterData;
  seo: SeoData;
  settings: {
    show_share_buttons: boolean;
  };
}

export function PublicLayout({
  children,
  branding,
  footer,
  seo,
  settings,
}: PublicLayoutProps) {
  return (
    <Box minH="100vh" display="flex" flexDirection="column" bg="white">
      {/* SEO Meta Tags */}
      <SocialMetaTags
        title={seo.title}
        description={seo.description}
        ogImage={seo.og_image}
        canonicalUrl={seo.canonical_url}
        siteName={branding.name}
      />

      {/* Share Buttons (Tasks 3.19, 3.20, 3.21) */}
      {settings.show_share_buttons && (
        <ShareButtons
          pageUrl={seo.canonical_url}
          title={seo.title}
        />
      )}

      {/* Header */}
      <Box as="header" bg="white" borderBottom="1px" borderColor="gray.200" py={4}>
        <Container maxW="1200px" px={{ base: 4, md: 8 }}>
          <Flex justify="space-between" align="center">
            <HStack spacing={3}>
              {branding.logo_url && (
                <Image
                  src={branding.logo_url}
                  alt={`${branding.name} logo`}
                  maxH={{ base: '36px', md: '48px' }}
                  objectFit="contain"
                  loading="lazy"
                />
              )}
              <Box>
                <Text fontWeight="bold" fontSize={{ base: 'lg', md: 'xl' }} color="gray.800">
                  {branding.name}
                </Text>
                {branding.tagline && (
                  <Text fontSize={{ base: 'xs', md: 'sm' }} color="gray.500" display={{ base: 'none', sm: 'block' }}>
                    {branding.tagline}
                  </Text>
                )}
              </Box>
            </HStack>
          </Flex>
        </Container>
      </Box>

      {/* Main Content */}
      <Box as="main" flex="1">
        <Box py={{ base: 0, md: 8 }}>
          {children}
        </Box>
      </Box>

      {/* Footer */}
      <PublicFooter footer={footer} />
    </Box>
  );
}
