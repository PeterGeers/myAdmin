import React from 'react';
import { Box, Button, Container, Flex, Heading, Text } from '@chakra-ui/react';

export interface CtaBlockProps {
  properties: {
    title: string;
    subtitle?: string;
    button_text?: string;
    button_url?: string;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Call-to-action block renderer — prominent banner with action button.
 *
 * Layout variants:
 * - centered: Full-width banner with centered text and button
 * - left-aligned: Text on left, button on right
 */
export const CtaBlock: React.FC<CtaBlockProps> = ({
  properties,
  layout,
}) => {
  const { title, subtitle, button_text, button_url } = properties || {};

  const isExternalUrl = button_url
    ? /^https?:\/\//.test(button_url)
    : false;

  const ctaButton = button_text ? (
    <Button
      as="a"
      href={button_url || '#'}
      target={isExternalUrl ? '_blank' : undefined}
      rel={isExternalUrl ? 'noopener noreferrer' : undefined}
      size="lg"
      bg="white"
      color="orange.500"
      fontWeight="bold"
      _hover={{ bg: 'gray.100' }}
      px={8}
    >
      {button_text}
    </Button>
  ) : null;

  // Layout: split — text left, button right
  if (layout === 'split') {
    return (
      <Box bgGradient="linear(to-r, orange.400, orange.500)" color="white" py={{ base: 10, md: 14 }}>
        <Container maxW="1200px" px={{ base: 6, md: 12 }}>
          <Flex direction={{ base: 'column', md: 'row' }} align="center" justify="space-between" gap={6}>
            <Box>
              <Heading as="h2" size="lg" mb={subtitle ? 2 : 0}>{title}</Heading>
              {subtitle && <Text fontSize="lg" opacity={0.9}>{subtitle}</Text>}
            </Box>
            {ctaButton}
          </Flex>
        </Container>
      </Box>
    );
  }

  // Layout: banner — thin full-width strip
  if (layout === 'banner') {
    return (
      <Box bgGradient="linear(to-r, orange.400, orange.500)" color="white" py={4}>
        <Container maxW="1200px" px={{ base: 6, md: 12 }}>
          <Flex align="center" justify="center" gap={4} wrap="wrap">
            <Text fontWeight="bold">{title}</Text>
            {subtitle && <Text opacity={0.9}>{subtitle}</Text>}
            {ctaButton}
          </Flex>
        </Container>
      </Box>
    );
  }

  // Layout: floating — fixed bottom bar (in preview, shown as sticky bottom-anchored box)
  if (layout === 'floating') {
    return (
      <Box position="sticky" bottom={0} left={0} right={0} bg="orange.600" color="white" py={3} px={6} zIndex={10} boxShadow="0 -2px 8px rgba(0,0,0,0.15)">
        <Flex align="center" justify="space-between" maxW="1200px" mx="auto" wrap="wrap" gap={3}>
          <Text fontWeight="bold">{title}</Text>
          {ctaButton}
        </Flex>
      </Box>
    );
  }

  // Layout: left-aligned — text left, button right
  if (layout === 'left-aligned') {
    return (
      <Box
        bgGradient="linear(to-r, orange.400, orange.500)"
        color="white"
        py={{ base: 10, md: 14 }}
      >
        <Container maxW="1200px" px={{ base: 6, md: 12 }}>
          <Flex
            direction={{ base: 'column', md: 'row' }}
            align="center"
            justify="space-between"
            gap={6}
          >
            <Box>
              <Heading as="h2" size="lg" mb={subtitle ? 2 : 0}>
                {title}
              </Heading>
              {subtitle && (
                <Text fontSize="lg" opacity={0.9}>
                  {subtitle}
                </Text>
              )}
            </Box>
            {ctaButton}
          </Flex>
        </Container>
      </Box>
    );
  }

  // Default: centered layout
  return (
    <Box
      bgGradient="linear(to-r, orange.400, orange.500)"
      color="white"
      py={{ base: 12, md: 16 }}
      textAlign="center"
    >
      <Container maxW="800px" px={{ base: 6, md: 12 }}>
        <Heading as="h2" size="xl" mb={subtitle ? 4 : 6}>
          {title}
        </Heading>
        {subtitle && (
          <Text fontSize="lg" opacity={0.9} mb={6}>
            {subtitle}
          </Text>
        )}
        {ctaButton}
      </Container>
    </Box>
  );
};
