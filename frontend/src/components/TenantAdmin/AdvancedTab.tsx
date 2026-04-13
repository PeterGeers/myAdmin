/**
 * Advanced Tab - Raw data management (SysAdmin only)
 * 
 * Shows ParameterManagement for raw parameter access.
 * Only visible to SysAdmin users (parent handles visibility).
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
