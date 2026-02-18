/**
 * 404 Not Found Page
 * 
 * Displayed when a user navigates to a non-existent route.
 */

import React from 'react';
import { Box, Heading, Text, Button, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';

const NotFound: React.FC = () => {
  const { t } = useTypedTranslation('errors');

  const handleGoHome = () => {
    window.location.href = '/';
  };

  return (
    <Box
      minH="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      bg="gray.900"
      color="white"
    >
      <VStack spacing={6} textAlign="center" px={4}>
        <Heading size="2xl" color="orange.400">
          {t('pages.notFound.title')}
        </Heading>
        <Text fontSize="lg" color="gray.300" maxW="md">
          {t('pages.notFound.message')}
        </Text>
        <Button
          colorScheme="orange"
          size="lg"
          onClick={handleGoHome}
        >
          {t('pages.notFound.action')}
        </Button>
      </VStack>
    </Box>
  );
};

export default NotFound;
