import React from 'react';
import { Box, VStack, Alert, AlertIcon } from '@chakra-ui/react';
import BnbReportsGroup from './reports/BnbReportsGroup';
import FinancialReportsGroup from './reports/FinancialReportsGroup';
import { useAuth } from '../context/AuthContext';

interface MyAdminReportsNewProps {
  reportType?: 'FIN' | 'STR';
}

const MyAdminReportsNew: React.FC<MyAdminReportsNewProps> = ({ reportType }) => {
  const { user } = useAuth();

  // Check if user has access to BNB (STR) reports
  // STR module permissions: STR_CRUD, STR_Read, STR_Export
  const canAccessBnbReports = user?.roles?.some(role => 
    ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role)
  );

  // Check if user has access to Financial reports
  // Finance module permissions: Finance_CRUD, Finance_Read, Finance_Export
  const canAccessFinancialReports = user?.roles?.some(role => 
    ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role)
  );

  // If reportType is specified, show only that type
  if (reportType === 'FIN') {
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
  }

  if (reportType === 'STR') {
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
  }

  // Legacy: If no reportType specified, show error (should not happen)
  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <Alert status="error">
        <AlertIcon />
        Invalid report type. Please use the menu to access FIN Reports or STR Reports.
      </Alert>
    </Box>
  );
};

export default MyAdminReportsNew;
