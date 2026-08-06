import React from 'react';
import { Box, Container, Heading, Text } from '@chakra-ui/react';

export interface EmbedBlockProps {
  properties: {
    url: string;
    height?: string;
    title?: string;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Embed block renderer — sandboxed iframe for external content.
 *
 * Layout variants:
 * - full-width: Iframe spans full container width
 * - contained: Iframe in a max-width container
 *
 * Security:
 * - HTTPS-only: shows error if URL doesn't start with https://
 * - Sandboxed: allow-scripts allow-same-origin (no allow-top-navigation)
 */
export const EmbedBlock: React.FC<EmbedBlockProps> = ({
  properties,
  layout,
}) => {
  const { url, height = '500px', title } = properties || {};

  // HTTPS-only validation
  const isValidUrl = url && url.startsWith('https://');

  const content = (
    <>
      {title && (
        <Heading as="h2" size="lg" mb={4}>
          {title}
        </Heading>
      )}
      {!isValidUrl ? (
        <Box
          bg="red.50"
          border="1px solid"
          borderColor="red.200"
          borderRadius="md"
          p={6}
          textAlign="center"
        >
          <Text color="red.600" fontWeight="semibold">
            Embed unavailable: Only HTTPS URLs are supported.
          </Text>
          {url && (
            <Text color="red.500" fontSize="sm" mt={2}>
              Provided URL: {url}
            </Text>
          )}
        </Box>
      ) : (
        <Box
          as="iframe"
          src={url}
          title={title || 'Embedded content'}
          sandbox="allow-scripts allow-same-origin"
          w="100%"
          h={height}
          border="none"
          borderRadius="md"
          boxShadow="sm"
        />
      )}
    </>
  );

  if (layout === 'contained') {
    return (
      <Container maxW="800px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {content}
      </Container>
    );
  }

  // Default: full-width
  return (
    <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {content}
    </Container>
  );
};
