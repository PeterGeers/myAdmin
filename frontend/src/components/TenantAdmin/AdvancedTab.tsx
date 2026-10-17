/**
 * Advanced Tab - Raw data management (tenant administrator)
 *
 * Shows ParameterManagement for raw parameter access, scoped to the current
 * tenant. Visible to any Tenant_Admin of the tenant (parent gates on the
 * dashboard's Tenant_Admin guard). The backend (`/api/tenant-admin/parameters`)
 * restricts rows to this tenant + its ACTIVE modules and masks secrets for
 * non-SysAdmin callers, so no extra SysAdmin-only gate belongs here.
 */

import React from 'react';
import {
  Box, Accordion, AccordionItem, AccordionButton, AccordionPanel,
  AccordionIcon, Text,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import ParameterManagement from './ParameterManagement';

interface AdvancedTabProps {
  tenant: string;
}

export default function AdvancedTab({ tenant }: AdvancedTabProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <Box>
      <Accordion allowMultiple defaultIndex={[0]}>
        {/* Raw Parameters */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">
                🔧 {t('tenantAdmin.tabs.parameters')}
              </Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <ParameterManagement tenant={tenant} />
          </AccordionPanel>
        </AccordionItem>
      </Accordion>
    </Box>
  );
}
