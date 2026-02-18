/**
 * 500 Server Error Page
 * 
 * Displayed when a server error occurs.
 */

import React from 'react';
import { Box, Heading, Text, Button, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';

const ServerError: React.FC = () => {
  const { t } = useTypedTranslation('errors');

  const handleRefresh = () => {
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
        <Heading size="2xl" color="red.400">
          {t('pages.serverError.title')}
        </Heading>
        <Text fontSize="lg" color="gray.300" maxW="md">
          {t('pages.serverError.message')}
        </Text>
        <Button
          colorScheme="orange"
          size="lg"
          onClick={handleRefresh}
        >
          {t('pages.serverError.action')}
        </Button>
      </VStack>
    </Box>
  );
};

export default ServerError;
