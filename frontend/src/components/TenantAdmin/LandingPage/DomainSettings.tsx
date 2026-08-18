/**
 * DomainSettings — Main domain management panel.
 *
 * Container component that loads domain configuration and renders
 * JabakiSubdomain and CustomDomainForm sub-components.
 *
 * Task 5.1
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, Text, Spinner, Alert, AlertIcon, Button, Divider,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { getDomains, DomainsResponse } from '../../../services/domainApi';
import JabakiSubdomain from './JabakiSubdomain';
import CustomDomainForm from './CustomDomainForm';

export default function DomainSettings() {
  const { t } = useTypedTranslation('admin');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);

  const loadDomains = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDomains();
      setDomains(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load domain settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDomains();
  }, [loadDomains]);

  if (loading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minH="200px">
        <Spinner size="lg" color="orange.400" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert status="error" bg="red.900" borderRadius="md">
        <AlertIcon />
        <Text color="white">{error}</Text>
        <Button ml="auto" size="sm" onClick={loadDomains}>
          {t('landingPage.domains.retry') || 'Retry'}
        </Button>
      </Alert>
    );
  }

  if (!domains) return null;

  return (
    <VStack spacing={6} align="stretch" color="gray.100">
      <Text color="white" fontWeight="bold" fontSize="lg">
        {t('landingPage.domains.title') || 'Domain Settings'}
      </Text>
      <Text color="gray.400" fontSize="sm">
        {t('landingPage.domains.description') || 'Configure how visitors reach your landing page.'}
      </Text>

      {/* Jabaki Subdomain Section */}
      <JabakiSubdomain
        jabaki={domains.jabaki}
        onUpdate={loadDomains}
      />

      <Divider borderColor="gray.600" />

      {/* Custom Domain Section */}
      <CustomDomainForm
        custom={domains.custom}
        onUpdate={loadDomains}
      />
    </VStack>
  );
}
