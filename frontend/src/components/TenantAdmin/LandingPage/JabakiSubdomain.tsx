/**
 * JabakiSubdomain — Toggle switch with preview URL for slug.jabaki.nl.
 *
 * Allows the tenant admin to enable/disable the Jabaki subdomain.
 * Shows the subdomain URL as a clickable link when enabled.
 *
 * Task 5.2
 */

import React, { useState } from 'react';
import {
  Box, HStack, VStack, Text, Switch, Link, Badge, useToast,
  FormControl, FormLabel,
} from '@chakra-ui/react';
import { ExternalLinkIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { enableJabaki, disableJabaki, JabakiStatus } from '../../../services/domainApi';

interface JabakiSubdomainProps {
  jabaki: JabakiStatus;
  onUpdate: () => void;
}

export default function JabakiSubdomain({ jabaki, onUpdate }: JabakiSubdomainProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();
  const [toggling, setToggling] = useState(false);

  const handleToggle = async () => {
    setToggling(true);
    try {
      if (jabaki.enabled) {
        await disableJabaki();
        toast({
          title: t('landingPage.domains.jabakiDisabled') || 'Jabaki subdomain disabled',
          status: 'info',
          duration: 3000,
        });
      } else {
        const result = await enableJabaki();
        toast({
          title: t('landingPage.domains.jabakiEnabled') || 'Jabaki subdomain enabled',
          description: result.domain,
          status: 'success',
          duration: 3000,
        });
      }
      onUpdate();
    } catch (err) {
      toast({
        title: t('landingPage.domains.jabakiError') || 'Error',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setToggling(false);
    }
  };

  const hasNoSlug = jabaki.status === 'no_slug';

  return (
    <Box bg="gray.800" p={4} borderRadius="md" border="1px solid" borderColor="gray.700">
      <VStack spacing={3} align="stretch">
        <HStack justify="space-between">
          <Text color="white" fontWeight="bold" fontSize="sm">
            {t('landingPage.domains.jabakiTitle') || 'Jabaki Subdomain'}
          </Text>
          {jabaki.enabled && (
            <Badge colorScheme="green" fontSize="xs">
              {t('landingPage.domains.statusActive') || 'Active'}
            </Badge>
          )}
        </HStack>

        <Text color="gray.400" fontSize="xs">
          {t('landingPage.domains.jabakiDescription') || 'Free subdomain on jabaki.nl — no DNS setup required.'}
        </Text>

        {hasNoSlug ? (
          <Text color="yellow.300" fontSize="xs">
            {t('landingPage.domains.noSlugWarning') || 'Set a slug first before enabling the Jabaki subdomain.'}
          </Text>
        ) : (
          <>
            <FormControl display="flex" alignItems="center">
              <Switch
                id="jabaki-toggle"
                isChecked={jabaki.enabled}
                onChange={handleToggle}
                isDisabled={toggling}
                colorScheme="orange"
                size="md"
                mr={3}
              />
              <FormLabel htmlFor="jabaki-toggle" color="gray.300" fontSize="sm" mb={0}>
                {jabaki.enabled
                  ? (t('landingPage.domains.jabakiEnabledLabel') || 'Subdomain is active')
                  : (t('landingPage.domains.jabakiDisabledLabel') || 'Enable subdomain')
                }
              </FormLabel>
            </FormControl>

            {jabaki.domain && (
              <HStack spacing={2}>
                <Text color="gray.400" fontSize="xs">URL:</Text>
                <Link
                  href={`https://${jabaki.domain}`}
                  isExternal
                  color="orange.300"
                  fontSize="sm"
                  fontFamily="mono"
                >
                  {jabaki.domain} <ExternalLinkIcon mx="2px" />
                </Link>
              </HStack>
            )}
          </>
        )}
      </VStack>
    </Box>
  );
}
