import React from 'react';
import { Box, Tab, TabList, TabPanel, TabPanels, Tabs, VStack, Alert, AlertIcon } from '@chakra-ui/react';
import BnbReportsGroup from './reports/BnbReportsGroup';
import FinancialReportsGroup from './reports/FinancialReportsGroup';
import { useAuth } from '../context/AuthContext';

const MyAdminReportsNew: React.FC = () => {
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

  // If user has no access to any reports, show message
  if (!canAccessBnbReports && !canAccessFinancialReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="warning">
          <AlertIcon />
          You do not have permission to access any reports. Please contact your administrator.
        </Alert>
      </Box>
    );
  }

  // If user only has access to one type of report, show it directly without tabs
  if (canAccessFinancialReports && !canAccessBnbReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <VStack spacing={6} align="stretch">
          <FinancialReportsGroup />
        </VStack>
      </Box>
    );
  }

  if (canAccessBnbReports && !canAccessFinancialReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <VStack spacing={6} align="stretch">
          <BnbReportsGroup />
        </VStack>
      </Box>
    );
  }

  // User has access to both - show tabs
  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <Tabs variant="enclosed" colorScheme="orange">
          <TabList>
            {canAccessBnbReports && <Tab color="white">🏠 BNB Reports</Tab>}
            {canAccessFinancialReports && <Tab color="white">💰 Financial Reports</Tab>}
          </TabList>

          <TabPanels>
            {canAccessBnbReports && (
              <TabPanel>
                <BnbReportsGroup />
              </TabPanel>
            )}

            {canAccessFinancialReports && (
              <TabPanel>
                <FinancialReportsGroup />
              </TabPanel>
            )}
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default MyAdminReportsNew;
