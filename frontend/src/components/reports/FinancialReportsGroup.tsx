import React, { useCallback, useEffect, useState } from 'react';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';

// Import individual report components
import MutatiesReport from './MutatiesReport';
import BalanceReport from './BalanceReport';
import ProfitLossReport from './ProfitLossReport';
import BtwReport from './BtwReport';
import ReferenceAnalysisReport from './ReferenceAnalysisReport';
import AangifteIbReport from './AangifteIbReport';

import type { DisplayFormat } from '../../types/financialReports';

const FinancialReportsGroup: React.FC = () => {
  const { t } = useTypedTranslation('reports');
  const { currentTenant } = useTenant();

  // Shared filter state — synced across Balance and P&L tabs
  const [selectedYears, setSelectedYears] = useState<string[]>([
    new Date().getFullYear().toString(),
  ]);
  const [displayFormat, setDisplayFormat] = useState<DisplayFormat>('2dec');
  const [availableYears, setAvailableYears] = useState<string[]>([]);

  const fetchAvailableYears = useCallback(async () => {
    if (!currentTenant) return;
    try {
      const params = new URLSearchParams({ administration: currentTenant });
      const resp = await authenticatedGet(buildEndpoint('/api/reports/available-years', params));
      const data = await resp.json();
      if (data.success) {
        setAvailableYears(data.years ?? []);
      }
    } catch {
      // Non-critical — year filter will just be empty
    }
  }, [currentTenant]);

  useEffect(() => {
    fetchAvailableYears();
  }, [fetchAvailableYears]);

  return (
    <Tabs variant="soft-rounded" colorScheme="orange" mt={4}>
      <TabList>
        <Tab color="white">💰 {t('titles.mutaties')}</Tab>
        <Tab color="white">📊 {t('titles.balanceSheet')}</Tab>
        <Tab color="white">📈 {t('titles.profitLoss')}</Tab>
        <Tab color="white">🧾 {t('titles.btwReport')}</Tab>
        <Tab color="white">🔍 {t('titles.referenceAnalysis')}</Tab>
        <Tab color="white">📋 {t('titles.aangifteIb')}</Tab>
      </TabList>

      <TabPanels>
        <TabPanel>
          <MutatiesReport />
        </TabPanel>

        <TabPanel>
          <BalanceReport
            selectedYears={selectedYears}
            displayFormat={displayFormat}
            availableYears={availableYears}
            onYearsChange={setSelectedYears}
            onDisplayFormatChange={setDisplayFormat}
          />
        </TabPanel>

        <TabPanel>
          <ProfitLossReport
            selectedYears={selectedYears}
            displayFormat={displayFormat}
            availableYears={availableYears}
            onYearsChange={setSelectedYears}
            onDisplayFormatChange={setDisplayFormat}
          />
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
