import React from 'react';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';

// Import individual report components
import MutatiesReport from './MutatiesReport';
import ActualsReport from './ActualsReport';
import BtwReport from './BtwReport';
import ReferenceAnalysisReport from './ReferenceAnalysisReport';
import AangifteIbReport from './AangifteIbReport';

const FinancialReportsGroup: React.FC = () => {
  const { t } = useTranslation('reports');

  return (
    <Tabs variant="soft-rounded" colorScheme="orange" mt={4}>
      <TabList>
        <Tab color="white">💰 {t('titles.mutaties')}</Tab>
        <Tab color="white">📊 {t('titles.actuals')}</Tab>
        <Tab color="white">🧾 {t('titles.btwReport')}</Tab>
        <Tab color="white">📈 {t('titles.referenceAnalysis')}</Tab>
        <Tab color="white">📋 {t('titles.aangifteIb')}</Tab>
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
}

export default FinancialReportsGroup;
