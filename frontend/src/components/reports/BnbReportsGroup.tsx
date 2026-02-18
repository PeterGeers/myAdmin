import React from 'react';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';

// Import individual report components
import BnbRevenueReport from './BnbRevenueReport';
import BnbActualsReport from './BnbActualsReport';
import BnbViolinsReport from './BnbViolinsReport';
import BnbReturningGuestsReport from './BnbReturningGuestsReport';
import BnbFutureReport from './BnbFutureReport';
import ToeristenbelastingReport from './ToeristenbelastingReport';
import BnbCountryBookingsReport from './BnbCountryBookingsReport';

const BnbReportsGroup: React.FC = () => {
  const { t } = useTranslation('reports');

  return (
    <Tabs variant="soft-rounded" colorScheme="orange" mt={4}>
      <TabList>
        <Tab color="white">🏠 {t('titles.bnbRevenue')}</Tab>
        <Tab color="white">🏡 {t('titles.bnbActuals')}</Tab>
        <Tab color="white">🎻 {t('titles.bnbViolins')}</Tab>
        <Tab color="white">🔄 {t('titles.bnbReturningGuests')}</Tab>
        <Tab color="white">📈 {t('titles.bnbFuture')}</Tab>
        <Tab color="white">🏨 {t('titles.toeristenbelasting')}</Tab>
        <Tab color="white">🌍 {t('titles.bnbCountryBookings')}</Tab>
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
