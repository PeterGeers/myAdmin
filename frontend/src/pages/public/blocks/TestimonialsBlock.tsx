import React from 'react';
import {
  Box,
  Container,
  Flex,
  Heading,
  Image,
  SimpleGrid,
  Text,
} from '@chakra-ui/react';

export interface TestimonialsBlockProps {
  properties: {
    title?: string;
    items: Array<{
      quote: string;
      author: string;
      role?: string;
      avatar_key?: string;
    }>;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Testimonials block renderer — displays quote cards.
 *
 * Layout variants:
 * - cards: Grid of quote cards
 * - slider: Horizontal display of testimonials
 */
export const TestimonialsBlock: React.FC<TestimonialsBlockProps> = ({
  properties,
  layout,
  cloudFrontUrl,
}) => {
  const { title, items } = properties || {};

  if (!items || items.length === 0) return null;

  const testimonialCard = (
    item: TestimonialsBlockProps['properties']['items'][number],
    index: number,
  ) => (
    <Box
      key={index}
      bg="white"
      p={6}
      borderRadius="lg"
      boxShadow="md"
      border="1px solid"
      borderColor="gray.100"
    >
      <Text fontStyle="italic" fontSize="md" color="gray.700" mb={4}>
        &ldquo;{item.quote}&rdquo;
      </Text>
      <Flex align="center" gap={3}>
        {item.avatar_key && (
          <Image
            src={`${cloudFrontUrl}/${item.avatar_key}`}
            alt={item.author}
            boxSize="40px"
            borderRadius="full"
            objectFit="cover"
            loading="lazy"
          />
        )}
        <Box>
          <Text fontWeight="bold" fontSize="sm">
            {item.author}
          </Text>
          {item.role && (
            <Text fontSize="xs" color="gray.500">
              {item.role}
            </Text>
          )}
        </Box>
      </Flex>
    </Box>
  );

  if (layout === 'slider') {
    return (
      <Box bg="gray.50" py={{ base: 12, md: 16 }}>
        <Container maxW="1200px" px={{ base: 6, md: 12 }}>
          {title && (
            <Heading as="h2" size="xl" textAlign="center" mb={8}>
              {title}
            </Heading>
          )}
          <Flex
            overflowX="auto"
            gap={6}
            pb={4}
            sx={{
              '&::-webkit-scrollbar': { height: '6px' },
              '&::-webkit-scrollbar-thumb': {
                bg: 'gray.300',
                borderRadius: 'full',
              },
            }}
          >
            {items.map((item, index) => (
              <Box key={index} minW="300px" maxW="400px" flex="0 0 auto">
                {testimonialCard(item, index)}
              </Box>
            ))}
          </Flex>
        </Container>
      </Box>
    );
  }

  // Default: cards layout
  return (
    <Box bg="gray.50" py={{ base: 12, md: 16 }}>
      <Container maxW="1200px" px={{ base: 6, md: 12 }}>
        {title && (
          <Heading as="h2" size="xl" textAlign="center" mb={8}>
            {title}
          </Heading>
        )}
        <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={6}>
          {items.map((item, index) => testimonialCard(item, index))}
        </SimpleGrid>
      </Container>
    </Box>
  );
};
