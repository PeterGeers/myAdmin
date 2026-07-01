import React from 'react';
import { Box, HStack, Text, Icon } from '@chakra-ui/react';
import { InfoIcon } from '@chakra-ui/icons';

/**
 * Shared wrapper for pipeline result sections.
 */
export function SectionBox({
  title,
  titleColor = 'gray.200',
  children,
}: {
  title: string;
  titleColor?: string;
  children: React.ReactNode;
}) {
  return (
    <Box
      p={4}
      bg="gray.700"
      borderRadius="lg"
      borderWidth="1px"
      borderColor="gray.600"
    >
      <Text fontSize="sm" fontWeight="bold" color={titleColor} mb={3}>
        {title}
      </Text>
      {children}
    </Box>
  );
}

/**
 * Label/value metric display.
 */
export function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Text fontSize="xs" color="gray.400">{label}</Text>
      <Text fontSize="sm" color="white" fontWeight="medium">{value}</Text>
    </Box>
  );
}

/**
 * Empty state placeholder with info icon.
 */
export function EmptyState({ message }: { message: string }) {
  return (
    <HStack spacing={2} py={2}>
      <Icon as={InfoIcon} color="gray.500" boxSize={3} />
      <Text fontSize="sm" color="gray.500" fontStyle="italic">
        {message}
      </Text>
    </HStack>
  );
}
