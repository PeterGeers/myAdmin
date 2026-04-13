/**
 * Tenant Info Tab - Consolidated view for Tenant Details + Email Log
 * 
 * Replaces the old separate TenantDetails and Email Log tabs.
 * Uses Accordion sections, all open by default.
 */

import React from 'react';
import {
  Box, Accordion, AccordionItem, AccordionButton, AccordionPanel,
  AccordionIcon, Text,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import TenantDetails from './TenantDetails';
import EmailLogPanel from '../shared/EmailLogPanel';

interface TenantInfoTabProps {
  tenant: string;
}

export default function TenantInfoTab({ tenant }: TenantInfoTabProps) {
  const { t } = useTypedTranslation('admin');

  return (
    <Box>
      <Accordion allowMultiple defaultIndex={[0, 1]}>
        {/* Tenant Details */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">
                {t('tenantAdmin.tabs.tenantDetails')}
              </Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <TenantDetails tenant={tenant} />
          </AccordionPanel>
        </AccordionItem>

        {/* Email Log */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">
                📧 {t('tenantAdmin.tabs.emailLog')}
              </Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <EmailLogPanel mode="tenant" />
          </AccordionPanel>
        </AccordionItem>
      </Accordion>
    </Box>
  );
}
