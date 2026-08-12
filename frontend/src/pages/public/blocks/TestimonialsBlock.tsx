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

  // Layout: carousel — single testimonial at a time, scrollable
  if (layout === 'carousel') {
    return (
      <Box bg="gray.50" py={{ base: 12, md: 16 }}>
        <Container maxW="800px" px={{ base: 6, md: 12 }} textAlign="center">
          {title && <Heading as="h2" size="xl" mb={8}>{title}</Heading>}
          {/* Show first item as preview in editor */}
          {items[0] && (
            <Box py={8}>
              <Text fontStyle="italic" fontSize="xl" color="gray.700" mb={4}>
                &ldquo;{items[0].quote}&rdquo;
              </Text>
              <Text fontWeight="bold">— {items[0].author}{items[0].role ? `, ${items[0].role}` : ''}</Text>
              {items.length > 1 && (
                <Text fontSize="sm" color="gray.400" mt={4}>
                  + {items.length - 1} more (carousel in published page)
                </Text>
              )}
            </Box>
          )}
        </Container>
      </Box>
    );
  }

  // Layout: quote-large — single large centered quote
  if (layout === 'quote-large') {
    const first = items[0];
    return (
      <Box py={{ base: 12, md: 16 }}>
        <Container maxW="800px" px={{ base: 6, md: 12 }} textAlign="center">
          {title && <Heading as="h2" size="xl" mb={8}>{title}</Heading>}
          {first && (
            <>
              <Text fontSize="2xl" fontStyle="italic" color="gray.700" lineHeight="tall">
                &ldquo;{first.quote}&rdquo;
              </Text>
              <Text fontWeight="bold" mt={6} fontSize="lg">
                — {first.author}{first.role ? `, ${first.role}` : ''}
              </Text>
            </>
          )}
        </Container>
      </Box>
    );
  }

  // Layout: grid — compact grid without card styling
  if (layout === 'grid') {
    return (
      <Box py={{ base: 12, md: 16 }}>
        <Container maxW="1200px" px={{ base: 6, md: 12 }}>
          {title && <Heading as="h2" size="xl" textAlign="center" mb={8}>{title}</Heading>}
          <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={6}>
            {items.map((item, index) => (
              <Box key={index} py={4} borderBottom="1px solid" borderColor="gray.200">
                <Text fontStyle="italic" color="gray.600" mb={2}>
                  &ldquo;{item.quote}&rdquo;
                </Text>
                <Text fontWeight="bold" fontSize="sm">
                  — {item.author}{item.role ? `, ${item.role}` : ''}
                </Text>
              </Box>
            ))}
          </SimpleGrid>
        </Container>
      </Box>
    );
  }

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
