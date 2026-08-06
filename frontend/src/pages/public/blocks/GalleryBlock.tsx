import React from 'react';
import { Box, Container, Heading, Image, SimpleGrid, Text } from '@chakra-ui/react';

export interface GalleryBlockProps {
  properties: {
    title?: string;
    images: Array<{
      key: string;
      alt?: string;
      caption?: string;
    }>;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Gallery block renderer — displays an image grid.
 *
 * Layout variants:
 * - grid-3: 3-column grid on desktop
 * - grid-4: 4-column grid on desktop
 * - masonry: Masonry-style layout (varied heights)
 */
export const GalleryBlock: React.FC<GalleryBlockProps> = ({
  properties,
  layout,
  cloudFrontUrl,
}) => {
  const { title, images } = properties || {};

  if (!images || images.length === 0) return null;

  const getColumns = () => {
    switch (layout) {
      case 'grid-4':
        return { base: 1, sm: 2, md: 3, lg: 4 };
      case 'masonry':
        return { base: 1, sm: 2, md: 3 };
      case 'grid-3':
      default:
        return { base: 1, sm: 2, md: 3 };
    }
  };

  return (
    <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {title && (
        <Heading as="h2" size="xl" textAlign="center" mb={8}>
          {title}
        </Heading>
      )}
      <SimpleGrid columns={getColumns()} spacing={4}>
        {images.map((image, index) => (
          <Box
            key={image.key || index}
            borderRadius="md"
            overflow="hidden"
            position="relative"
          >
            <Image
              src={`${cloudFrontUrl}/${image.key}`}
              alt={image.alt || `Gallery image ${index + 1}`}
              objectFit="cover"
              w="100%"
              h={layout === 'masonry' ? 'auto' : '250px'}
              minH={layout === 'masonry' ? '200px' : undefined}
              transition="transform 0.2s"
              _hover={{ transform: 'scale(1.02)' }}
              loading="lazy"
            />
            {image.caption && (
              <Text
                fontSize="sm"
                color="gray.600"
                mt={2}
                textAlign="center"
                px={1}
              >
                {image.caption}
              </Text>
            )}
          </Box>
        ))}
      </SimpleGrid>
    </Container>
  );
};
