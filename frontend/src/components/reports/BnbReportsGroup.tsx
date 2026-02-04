import React from 'react';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from '@chakra-ui/react';

// Import individual report components
import BnbRevenueReport from './BnbRevenueReport';
import BnbActualsReport from './BnbActualsReport';
import BnbViolinsReport from './BnbViolinsReport';
import BnbReturningGuestsReport from './BnbReturningGuestsReport';
import BnbFutureReport from './BnbFutureReport';
import ToeristenbelastingReport from './ToeristenbelastingReport';
import BnbCountryBookingsReport from './BnbCountryBookingsReport';

const BnbReportsGroup: React.FC = () => {
  return (
    <Tabs variant="soft-rounded" colorScheme="orange" mt={4}>
      <TabList>
        <Tab color="white">🏠 Revenue</Tab>
        <Tab color="white">🏡 Actuals</Tab>
        <Tab color="white">🎻 Violins</Tab>
        <Tab color="white">🔄 Terugkerend</Tab>
        <Tab color="white">📈 Future</Tab>
        <Tab color="white">🏨 Toeristenbelasting</Tab>
        <Tab color="white">🌍 Country Bookings</Tab>
      </TabList>

      <TabPanels>
        <TabPanel>
          <BnbRevenueReport />
        </TabPanel>
        
        <TabPanel>
          <BnbActualsReport />
        </TabPanel>
        
        <TabPanel>
          <BnbViolinsReport />
        </TabPanel>
        
        <TabPanel>
          <BnbReturningGuestsReport />
        </TabPanel>
        
        <TabPanel>
          <BnbFutureReport />
        </TabPanel>
        
        <TabPanel>
          <ToeristenbelastingReport />
        </TabPanel>
        
        <TabPanel>
          <BnbCountryBookingsReport />
        </TabPanel>
      </TabPanels>
    </Tabs>
  );
};

export default BnbReportsGroup;
