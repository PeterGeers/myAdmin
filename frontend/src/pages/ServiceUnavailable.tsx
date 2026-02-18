/**
 * 503 Service Unavailable Page
 * 
 * Displayed when the service is temporarily unavailable.
 */

import React from 'react';
import { Box, Heading, Text, Button, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';

const ServiceUnavailable: React.FC = () => {
  const { t } = useTypedTranslation('errors');

  const handleRetry = () => {
    window.location.reload();
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
        <Heading size="2xl" color="yellow.400">
          {t('pages.serviceUnavailable.title')}
        </Heading>
        <Text fontSize="lg" color="gray.300" maxW="md">
          {t('pages.serviceUnavailable.message')}
        </Text>
        <Button
          colorScheme="orange"
          size="lg"
          onClick={handleRetry}
        >
          {t('pages.serviceUnavailable.action')}
        </Button>
      </VStack>
    </Box>
  );
};

export default ServiceUnavailable;
