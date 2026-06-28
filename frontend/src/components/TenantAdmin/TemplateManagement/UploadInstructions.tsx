/**
 * Upload Instructions Component
 *
 * Help text box with step-by-step upload instructions.
 */

import React from 'react';
import {
  Box,
  VStack,
  Text,
} from '@chakra-ui/react';

export const UploadInstructions: React.FC = () => {
  return (
    <Box bg="blue.900" p={4} borderRadius="md">
      <Text fontSize="sm" fontWeight="bold" mb={2}>
        📝 Upload Instructions
      </Text>
      <VStack align="start" spacing={1} fontSize="xs" color="gray.300">
        <Text>1. Select the template type from the dropdown</Text>
        <Text>2. Choose your HTML template file (max 5MB)</Text>
        <Text>3. Optionally configure field mappings</Text>
        <Text>4. Click "Upload & Preview Template" to validate</Text>
      </VStack>
    </Box>
  );
};

export default UploadInstructions;
