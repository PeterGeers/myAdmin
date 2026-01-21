import React from 'react';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from '@chakra-ui/react';

// Import individual report components
import MutatiesReport from './MutatiesReport';
import ActualsReport from './ActualsReport';
import BtwReport from './BtwReport';
import ReferenceAnalysisReport from './ReferenceAnalysisReport';
import AangifteIbReport from './AangifteIbReport';

const FinancialReportsGroup: React.FC = () => {
  return (
    <Tabs variant="soft-rounded" colorScheme="orange" mt={4}>
      <TabList>
        <Tab color="white">💰 Mutaties (P&L)</Tab>
        <Tab color="white">📊 Actuals</Tab>
        <Tab color="white">🧾 Aangifte BTW</Tab>
        <Tab color="white">📈 Trend by ReferenceNumber</Tab>
        <Tab color="white">📋 Aangifte IB</Tab>
      </TabList>

      <TabPanels>
        <TabPanel>
          <MutatiesReport />
        </TabPanel>
        
        <TabPanel>
          <ActualsReport />
        </TabPanel>
        
        <TabPanel>
          <BtwReport />
        </TabPanel>
        
        <TabPanel>
          <ReferenceAnalysisReport />
        </TabPanel>
        
        <TabPanel>
          <AangifteIbReport />
        </TabPanel>
      </TabPanels>
    </Tabs>
  );
};

export default FinancialReportsGroup;
