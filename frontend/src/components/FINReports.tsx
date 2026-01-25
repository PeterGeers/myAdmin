import React from 'react';
import { Box, VStack, Alert, AlertIcon } from '@chakra-ui/react';
import FinancialReportsGroup from './reports/FinancialReportsGroup';
import { useAuth } from '../context/AuthContext';

const FINReports: React.FC = () => {
  const { user } = useAuth();

  // Check if user has access to Financial reports
  // Finance module permissions: Finance_CRUD, Finance_Read, Finance_Export
  const canAccessFinancialReports = user?.roles?.some(role => 
    ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role)
  );

  if (!canAccessFinancialReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="warning">
          <AlertIcon />
          You do not have permission to access Financial reports. Please contact your administrator.
        </Alert>
      </Box>
    );
  }

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <FinancialReportsGroup />
      </VStack>
    </Box>
  );
};

export default FINReports;
