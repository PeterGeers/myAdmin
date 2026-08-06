import React from 'react';
import { Box, Flex, Heading, Text, Image } from '@chakra-ui/react';

export interface AboutBlockProps {
  properties: {
    content_md: string;
    image_key?: string;
    title?: string;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * About/content section block renderer.
 *
 * Layout variants:
 * - centered: Text centered, optional image below
 * - image-left: Image on left, text on right
 * - image-right: Text on left, image on right
 */
export const AboutBlock: React.FC<AboutBlockProps> = ({
  properties,
  layout,
  cloudFrontUrl,
}) => {
  const { content_md, image_key, title } = properties || {};
  const imageUrl = image_key ? `${cloudFrontUrl}/${image_key}` : undefined;

  // Split content on newlines to render as paragraphs (Phase 1 — no markdown library)
  const paragraphs = (content_md || '')
    .split('\n')
    .filter((line) => line.trim().length > 0);

  const textContent = (
    <Box>
      {title && (
        <Heading as="h2" size="xl" fontWeight="bold" mb={4}>
          {title}
        </Heading>
      )}
      {paragraphs.map((paragraph, index) => (
        <Text key={index} mb={3} fontSize="md" lineHeight="tall">
          {paragraph}
        </Text>
      ))}
    </Box>
  );

  const imageElement = imageUrl ? (
    <Image
      src={imageUrl}
      alt={title || 'About image'}
      borderRadius="md"
      w="100%"
      h="auto"
      loading="lazy"
    />
  ) : null;

  // Layout: centered — text centered, optional image below
  if (layout === 'centered') {
    return (
      <Box
        maxW="800px"
        mx="auto"
        textAlign="center"
        px={{ base: 6, md: 12 }}
        py={{ base: 12, md: 16 }}
      >
        {textContent}
        {imageElement && <Box mt={8}>{imageElement}</Box>}
      </Box>
    );
  }

  // Layout: image-left or image-right (default to image-right)
  const isImageLeft = layout === 'image-left';

  return (
    <Flex
      direction={{ base: 'column', md: isImageLeft ? 'row' : 'row-reverse' }}
      align="center"
      gap={{ base: 6, md: 10 }}
      maxW="1200px"
      mx="auto"
      px={{ base: 6, md: 12 }}
      py={{ base: 12, md: 16 }}
    >
      {/* Image side */}
      {imageElement && <Box flex="1">{imageElement}</Box>}

      {/* Text side */}
      <Box flex="1">{textContent}</Box>
    </Flex>
  );
};
