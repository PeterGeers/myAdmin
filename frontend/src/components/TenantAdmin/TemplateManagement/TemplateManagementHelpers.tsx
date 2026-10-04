import React from 'react';
import { Box, VStack, Text } from '@chakra-ui/react';

// `getRequiredPlaceholders` has a single implementation (backed by the
// REQUIRED_PLACEHOLDERS map) in types/template.ts. Re-export it here so the
// existing `import { getRequiredPlaceholders } from './TemplateManagementHelpers'`
// call site keeps working without a second copy of the placeholder map.
export { getRequiredPlaceholders } from '../../../types/template';

/**
 * Helper function to read file as text
 */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        resolve(e.target.result as string);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

/**
 * Step Indicator Component
 */
interface StepIndicatorProps {
  number: number;
  label: string;
  isActive: boolean;
  isCompleted: boolean;
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({ number, label, isActive, isCompleted }) => {
  const status = isCompleted ? 'completed' : isActive ? 'current' : 'upcoming';

  return (
    <VStack spacing={2}>
      <Box
        w="40px"
        h="40px"
        borderRadius="full"
        bg={isActive ? 'brand.orange' : isCompleted ? 'green.500' : 'gray.700'}
        color="white"
        display="flex"
        alignItems="center"
        justifyContent="center"
        fontWeight="bold"
        aria-label={`Step ${number}: ${label}, ${status}`}
      >
        {number}
      </Box>
      <Text
        fontSize="sm"
        color={isActive ? 'brand.orange' : 'gray.400'}
        fontWeight={isActive ? 'bold' : 'normal'}
        aria-hidden="true"
      >
        {label}
      </Text>
    </VStack>
  );
};
