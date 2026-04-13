/**
 * Financial Tab - Consolidated view for Chart of Accounts + Tax Rates + VAT Netting
 * 
 * Replaces the old separate ChartOfAccounts, YearEndSettings, and TaxRates tabs.
 * Uses Accordion sections, all open by default.
 * FIN module gated (parent handles visibility).
 */

import React from 'react';
import {
  Box, Accordion, AccordionItem, AccordionButton, AccordionPanel,
  AccordionIcon, Text,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import ChartOfAccounts from './ChartOfAccounts';
import TaxRateManagement from './TaxRateManagement';

interface FinancialTabProps {
  tenant: string;
}

export default function FinancialTab({ tenant }: FinancialTabProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <Box>
      <Accordion allowMultiple defaultIndex={[0, 1]}>
        {/* Chart of Accounts */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">
                {t('tenantAdmin.tabs.chartOfAccounts')}
              </Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <ChartOfAccounts tenant={tenant} />
          </AccordionPanel>
        </AccordionItem>

        {/* Tax Rates */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">
                {t('tenantAdmin.tabs.taxRates')}
              </Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <TaxRateManagement tenant={tenant} />
          </AccordionPanel>
        </AccordionItem>
      </Accordion>
    </Box>
  );
}
