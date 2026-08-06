import React from 'react';
import { Box, Heading, Text, Button, VStack } from '@chakra-ui/react';

/**
 * Public 404 Not Found Page
 *
 * Displayed when a visitor navigates to a non-existent or unpublished
 * tenant landing page slug. Uses a light theme consistent with public pages.
 */
const NotFoundPage: React.FC = () => {
  const handleGoHome = () => {
    window.location.href = '/';
  };

  return (
    <Box
      minH="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      bg="gray.50"
      color="gray.800"
    >
      <VStack spacing={6} textAlign="center" px={4}>
        <Heading size="2xl" color="gray.700">
          404
        </Heading>
        <Heading size="lg" color="gray.600">
          Pagina niet gevonden
        </Heading>
        <Text fontSize="lg" color="gray.500" maxW="md">
          De pagina die je zoekt bestaat niet of is niet meer gepubliceerd.
        </Text>
        <Button
          colorScheme="blue"
          variant="outline"
          size="lg"
          onClick={handleGoHome}
        >
          Terug naar homepage
        </Button>
      </VStack>
    </Box>
  );
};

export default NotFoundPage;
