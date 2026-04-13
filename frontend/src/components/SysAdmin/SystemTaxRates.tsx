import React from 'react';
import { Box, Text } from '@chakra-ui/react';
import TaxRateManagement from '../TenantAdmin/TaxRateManagement';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

export default function SystemTaxRates() {
  const { t } = useTypedTranslation('admin');
  return (
    <Box>
      <Text color="gray.300" mb={4} fontSize="sm">
        {t('tenantAdmin.taxRates.systemRatesInfo')}
      </Text>
      <TaxRateManagement tenant="_system_" isSysAdmin={true} />
    </Box>
  );
}
