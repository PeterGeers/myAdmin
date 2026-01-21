import React from 'react';
import { Box, Tab, TabList, TabPanel, TabPanels, Tabs, VStack } from '@chakra-ui/react';
import BnbReportsGroup from './reports/BnbReportsGroup';
import FinancialReportsGroup from './reports/FinancialReportsGroup';

const MyAdminReportsNew: React.FC = () => {
  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <Tabs variant="enclosed" colorScheme="orange">
          <TabList>
            <Tab color="white">🏠 BNB Reports</Tab>
            <Tab color="white">💰 Financial Reports</Tab>
          </TabList>

          <TabPanels>
            {/* BNB Reports Group */}
            <TabPanel>
              <BnbReportsGroup />
            </TabPanel>

            {/* Financial Reports Group */}
            <TabPanel>
              <FinancialReportsGroup />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
};

export default MyAdminReportsNew;
