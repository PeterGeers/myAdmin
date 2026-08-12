import React from 'react';
import {
  Accordion,
  AccordionButton,
  AccordionIcon,
  AccordionItem,
  AccordionPanel,
  Box,
  Container,
  Flex,
  Heading,
  SimpleGrid,
  Text,
} from '@chakra-ui/react';

export interface FaqBlockProps {
  properties: {
    title?: string;
    items: Array<{
      question: string;
      answer: string;
    }>;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * FAQ block renderer — displays questions and answers.
 *
 * Layout variants:
 * - accordion: Clickable questions reveal answers (Chakra Accordion)
 * - list: Simple Q&A list with all answers visible
 */
export const FaqBlock: React.FC<FaqBlockProps> = ({
  properties,
  layout,
}) => {
  const { title, items } = properties || {};

  if (!items || items.length === 0) return null;

  // Layout: two-column — forced 2-column accordion
  if (layout === 'two-column') {
    return (
      <Container maxW="1000px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {title && <Heading as="h2" size="xl" textAlign="center" mb={8}>{title}</Heading>}
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
          {items.map((item, index) => (
            <Box key={index} borderBottom="1px solid" borderColor="gray.200" pb={3} mb={3}>
              <Text fontWeight="bold" mb={1}>{item.question}</Text>
              <Text color="gray.600" fontSize="sm">{item.answer}</Text>
            </Box>
          ))}
        </SimpleGrid>
      </Container>
    );
  }

  // Layout: side-by-side — question left, answer right
  if (layout === 'side-by-side') {
    return (
      <Container maxW="1000px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {title && <Heading as="h2" size="xl" textAlign="center" mb={8}>{title}</Heading>}
        {items.map((item, index) => (
          <Flex key={index} direction={{ base: 'column', md: 'row' }} gap={4} py={4} borderBottom="1px solid" borderColor="gray.200">
            <Box flex="1" fontWeight="bold">{item.question}</Box>
            <Box flex="2" color="gray.600">{item.answer}</Box>
          </Flex>
        ))}
      </Container>
    );
  }

  // Layout: list — all Q&A visible
  if (layout === 'list') {
    return (
      <Container maxW="800px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
        {title && (
          <Heading as="h2" size="xl" textAlign="center" mb={8}>
            {title}
          </Heading>
        )}
        {items.map((item, index) => (
          <Box key={index} mb={6}>
            <Text fontWeight="bold" fontSize="lg" mb={2}>
              {item.question}
            </Text>
            <Text color="gray.600" lineHeight="tall">
              {item.answer}
            </Text>
          </Box>
        ))}
      </Container>
    );
  }

  // Default: accordion layout
  return (
    <Container maxW="800px" px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {title && (
        <Heading as="h2" size="xl" textAlign="center" mb={8}>
          {title}
        </Heading>
      )}
      <Accordion allowMultiple>
        {items.map((item, index) => (
          <AccordionItem key={index} border="none" mb={2}>
            <AccordionButton
              bg="gray.50"
              borderRadius="md"
              _hover={{ bg: 'gray.100' }}
              _expanded={{ bg: 'gray.100' }}
              py={4}
              px={5}
            >
              <Box flex="1" textAlign="left" fontWeight="semibold">
                {item.question}
              </Box>
              <AccordionIcon />
            </AccordionButton>
            <AccordionPanel py={4} px={5} color="gray.600" lineHeight="tall">
              {item.answer}
            </AccordionPanel>
          </AccordionItem>
        ))}
      </Accordion>
    </Container>
  );
};
