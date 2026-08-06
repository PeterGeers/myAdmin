import React from 'react';
import {
  Box,
  Container,
  Flex,
  Heading,
  List,
  ListIcon,
  ListItem,
  SimpleGrid,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from '@chakra-ui/react';
import { CheckIcon } from '@chakra-ui/icons';

export interface PricingBlockProps {
  properties: {
    title?: string;
    items: Array<{
      name: string;
      price: string;
      period?: string;
      features?: string[];
      highlighted?: boolean;
    }>;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Pricing block renderer — displays rate/pricing information.
 *
 * Layout variants:
 * - cards: Pricing cards in a grid (highlighted card gets accent border)
 * - table: Tabular display of pricing tiers
 */
export const PricingBlock: React.FC<PricingBlockProps> = ({
  properties,
  layout,
}) => {
  const { title, items } = properties || {};

  if (!items || items.length === 0) return null;

  // Layout: table
  if (layout === 'table') {
    return (
      <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {title && (
          <Heading as="h2" size="xl" textAlign="center" mb={8}>
            {title}
          </Heading>
        )}
        <Box overflowX="auto">
          <Table variant="simple">
            <Thead>
              <Tr>
                <Th>Plan</Th>
                <Th>Price</Th>
                <Th>Features</Th>
              </Tr>
            </Thead>
            <Tbody>
              {items.map((item, index) => (
                <Tr
                  key={index}
                  bg={item.highlighted ? 'orange.50' : undefined}
                  fontWeight={item.highlighted ? 'semibold' : undefined}
                >
                  <Td>{item.name}</Td>
                  <Td>
                    {item.price}
                    {item.period && (
                      <Text as="span" fontSize="sm" color="gray.500" ml={1}>
                        /{item.period}
                      </Text>
                    )}
                  </Td>
                  <Td>{item.features?.join(', ')}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      </Container>
    );
  }

  // Default: cards layout
  return (
    <Container maxW="1200px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {title && (
        <Heading as="h2" size="xl" textAlign="center" mb={8}>
          {title}
        </Heading>
      )}
      <SimpleGrid
        columns={{ base: 1, md: items.length >= 3 ? 3 : items.length }}
        spacing={6}
      >
        {items.map((item, index) => (
          <Flex
            key={index}
            direction="column"
            align="center"
            bg="white"
            p={8}
            borderRadius="lg"
            boxShadow="md"
            border="2px solid"
            borderColor={item.highlighted ? 'orange.400' : 'gray.100'}
            position="relative"
          >
            {item.highlighted && (
              <Box
                position="absolute"
                top={-3}
                bg="orange.400"
                color="white"
                px={3}
                py={1}
                borderRadius="full"
                fontSize="xs"
                fontWeight="bold"
              >
                Popular
              </Box>
            )}
            <Heading as="h3" size="md" mb={2}>
              {item.name}
            </Heading>
            <Text fontSize="3xl" fontWeight="bold" mb={1}>
              {item.price}
            </Text>
            {item.period && (
              <Text fontSize="sm" color="gray.500" mb={4}>
                per {item.period}
              </Text>
            )}
            {item.features && item.features.length > 0 && (
              <List spacing={2} mt={4} textAlign="left" w="100%">
                {item.features.map((feature, fIndex) => (
                  <ListItem key={fIndex} fontSize="sm">
                    <ListIcon as={CheckIcon} color="green.500" />
                    {feature}
                  </ListItem>
                ))}
              </List>
            )}
          </Flex>
        ))}
      </SimpleGrid>
    </Container>
  );
};
