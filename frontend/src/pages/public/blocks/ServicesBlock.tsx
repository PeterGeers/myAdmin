import React from 'react';
import {
  Box,
  Container,
  Heading,
  SimpleGrid,
  Text,
  Badge,
  Flex,
} from '@chakra-ui/react';

export interface ServicesBlockProps {
  properties: {
    title?: string;
    items: Array<{
      id?: number | string;
      name: string;
      description?: string;
      price?: string;
      category?: string;
    }>;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Services block renderer — displays ZZP service/product listings.
 *
 * Layout variants:
 * - grid: Card grid (1 col mobile, 2 tablet, 3 desktop)
 * - list: Single-column list with larger cards
 */
export const ServicesBlock: React.FC<ServicesBlockProps> = ({
  properties,
  layout,
}) => {
  const { title, items } = properties || {};

  if (!items || items.length === 0) return null;

  // List layout: single column
  if (layout === 'list') {
    return (
      <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {title && (
          <Heading as="h2" size="xl" textAlign="center" mb={8}>
            {title}
          </Heading>
        )}
        <Flex direction="column" gap={4}>
          {items.map((item, index) => (
            <Box
              key={item.id || index}
              bg="white"
              p={6}
              borderRadius="lg"
              boxShadow="sm"
              border="1px solid"
              borderColor="gray.100"
              transition="box-shadow 0.2s"
              _hover={{ boxShadow: 'md' }}
            >
              <Flex
                justify="space-between"
                align={{ base: 'flex-start', md: 'center' }}
                direction={{ base: 'column', md: 'row' }}
                gap={3}
              >
                <Box flex="1">
                  <Flex align="center" gap={3} mb={1}>
                    <Heading as="h3" size="md">
                      {item.name}
                    </Heading>
                    {item.category && (
                      <Badge colorScheme="teal" variant="subtle">
                        {item.category}
                      </Badge>
                    )}
                  </Flex>
                  {item.description && (
                    <Text fontSize="sm" color="gray.600" mt={1}>
                      {item.description}
                    </Text>
                  )}
                </Box>
                {item.price && (
                  <Text
                    fontWeight="bold"
                    fontSize="lg"
                    color="var(--brand-primary, #2D6A4F)"
                    whiteSpace="nowrap"
                  >
                    {item.price}
                  </Text>
                )}
              </Flex>
            </Box>
          ))}
        </Flex>
      </Container>
    );
  }

  // Default: grid layout
  return (
    <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {title && (
        <Heading as="h2" size="xl" textAlign="center" mb={8}>
          {title}
        </Heading>
      )}
      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={6}>
        {items.map((item, index) => (
          <Box
            key={item.id || index}
            bg="white"
            p={6}
            borderRadius="lg"
            boxShadow="md"
            border="1px solid"
            borderColor="gray.100"
            transition="transform 0.2s, box-shadow 0.2s"
            _hover={{ transform: 'translateY(-2px)', boxShadow: 'lg' }}
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            h="100%"
          >
            <Box>
              {item.category && (
                <Badge colorScheme="teal" variant="subtle" mb={2}>
                  {item.category}
                </Badge>
              )}
              <Heading as="h3" size="md" mb={2}>
                {item.name}
              </Heading>
              {item.description && (
                <Text fontSize="sm" color="gray.600" noOfLines={3}>
                  {item.description}
                </Text>
              )}
            </Box>
            {item.price && (
              <Text
                fontWeight="bold"
                fontSize="lg"
                color="var(--brand-primary, #2D6A4F)"
                mt={4}
              >
                {item.price}
              </Text>
            )}
          </Box>
        ))}
      </SimpleGrid>
    </Container>
  );
};
