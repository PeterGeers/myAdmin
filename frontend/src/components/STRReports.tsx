import React from 'react';
import { Box, VStack, Alert, AlertIcon } from '@chakra-ui/react';
import BnbReportsGroup from './reports/BnbReportsGroup';
import { useAuth } from '../context/AuthContext';

const STRReports: React.FC = () => {
  const { user } = useAuth();

  // Check if user has access to BNB (STR) reports
  // STR module permissions: STR_CRUD, STR_Read, STR_Export
  const canAccessBnbReports = user?.roles?.some(role => 
    ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role)
  );

  if (!canAccessBnbReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="warning">
          <AlertIcon />
          You do not have permission to access STR reports. Please contact your administrator.
        </Alert>
      </Box>
    );
  }

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <BnbReportsGroup />
      </VStack>
    </Box>
  );
};

export default STRReports;
