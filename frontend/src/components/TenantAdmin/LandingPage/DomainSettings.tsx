/**
 * DomainSettings — Main domain management panel.
 *
 * Container component that loads domain configuration and renders
 * JabakiSubdomain and CustomDomainForm sub-components.
 * Also allows editing the tenant slug (URL prefix).
 *
 * Task 5.1
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Text, Spinner, Alert, AlertIcon, Button, Divider, Badge,
  useToast,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { getDomains, DomainsResponse } from '../../../services/domainApi';
import { getSlug, setSlug, validateSlug } from '../../../services/landingPageApi';
import JabakiSubdomain from './JabakiSubdomain';
import CustomDomainForm from './CustomDomainForm';

export default function DomainSettings() {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);

  // Slug editing state
  const [currentSlug, setCurrentSlug] = useState<string | null>(null);
  const [slugInput, setSlugInput] = useState('');
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugSaving, setSlugSaving] = useState(false);
  const [editingSlug, setEditingSlug] = useState(false);
  const [slugRenameConfirm, setSlugRenameConfirm] = useState(false);

  const loadDomains = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [domainsData, slugResp] = await Promise.all([getDomains(), getSlug()]);
      setDomains(domainsData);
      if (slugResp.success && slugResp.data?.slug) {
        setCurrentSlug(slugResp.data.slug);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load domain settings');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSlugSave = async () => {
    setSlugError(null);
    setSlugSaving(true);
    try {
      const valResp = await validateSlug(slugInput);
      if (!valResp.valid) {
        setSlugError(valResp.error || 'Invalid slug');
        setSlugSaving(false);
        return;
      }
      if (currentSlug && currentSlug !== slugInput && !slugRenameConfirm) {
        setSlugRenameConfirm(true);
        setSlugSaving(false);
        return;
      }
      const resp = await setSlug(slugInput);
      if (resp.success) {
        setCurrentSlug(slugInput);
        setEditingSlug(false);
        setSlugRenameConfirm(false);
        toast({
          title: resp.renamed_from
            ? t('landingPage.editor.slugRenamed')
            : t('landingPage.slug.saved'),
          description: resp.renamed_from ? `${resp.renamed_from} → ${slugInput}` : undefined,
          status: 'success',
          duration: 4000,
        });
        if (resp.warnings && resp.warnings.length > 0) {
          toast({ title: t('landingPage.editor.slugRenameWarnings'), description: resp.warnings.join(', '), status: 'warning', duration: 8000 });
        }
        loadDomains();
      } else {
        setSlugError(resp.error || 'Failed to save slug');
      }
    } catch (err) {
      setSlugError(err instanceof Error ? err.message : 'Failed to save slug');
    } finally {
      setSlugSaving(false);
    }
  };

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

      {/* Slug / URL prefix */}
      {currentSlug && (
        <Box p={3} bg="gray.700" borderRadius="md">
          <Text color="gray.300" fontSize="xs" mb={2} fontWeight="semibold">
            {t('landingPage.domains.slugLabel') || 'URL slug'}
          </Text>
          {!editingSlug ? (
            <HStack spacing={3}>
              <Badge colorScheme="orange" fontSize="sm">{currentSlug}.jabaki.nl</Badge>
              <Button
                size="xs"
                variant="ghost"
                colorScheme="orange"
                onClick={() => { setSlugInput(currentSlug); setEditingSlug(true); setSlugError(null); setSlugRenameConfirm(false); }}
              >
                {t('landingPage.editor.changeSlug')}
              </Button>
            </HStack>
          ) : (
            <VStack spacing={2} align="stretch">
              <HStack spacing={2}>
                <Box
                  as="input"
                  w="200px"
                  px={2}
                  py={1}
                  bg="gray.800"
                  color="white"
                  borderRadius="md"
                  border="1px solid"
                  borderColor={slugError ? 'red.400' : 'gray.600'}
                  fontSize="sm"
                  value={slugInput}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                    setSlugInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                    setSlugError(null);
                    setSlugRenameConfirm(false);
                  }}
                  _focus={{ borderColor: 'orange.400', outline: 'none' }}
                />
                <Text color="gray.500" fontSize="sm">.jabaki.nl</Text>
              </HStack>
              {slugRenameConfirm && (
                <Text color="yellow.300" fontSize="xs">
                  {t('landingPage.editor.slugRenameWarning')}
                </Text>
              )}
              <HStack spacing={2}>
                {slugRenameConfirm ? (
                  <Button size="xs" colorScheme="red" onClick={handleSlugSave} isLoading={slugSaving}>
                    {t('landingPage.editor.confirmRename')}
                  </Button>
                ) : (
                  <Button size="xs" colorScheme="orange" onClick={handleSlugSave} isLoading={slugSaving} isDisabled={slugInput.length < 3 || slugInput === currentSlug}>
                    {t('landingPage.editor.saveSlug')}
                  </Button>
                )}
                <Button size="xs" variant="ghost" colorScheme="orange" onClick={() => { setEditingSlug(false); setSlugError(null); setSlugRenameConfirm(false); }}>
                  {t('landingPage.editor.cancel')}
                </Button>
              </HStack>
              {slugError && <Text color="red.300" fontSize="xs">{slugError}</Text>}
            </VStack>
          )}
        </Box>
      )}

      <Divider borderColor="gray.600" />

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
