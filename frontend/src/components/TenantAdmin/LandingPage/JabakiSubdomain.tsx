/**
 * JabakiSubdomain — Toggle switch with preview URL for slug.jabaki.nl.
 *
 * Allows the tenant admin to enable/disable the Jabaki subdomain
 * and change the slug (URL prefix).
 *
 * Task 5.2
 */

import React, { useState } from 'react';
import {
  Box, HStack, VStack, Text, Switch, Link, Badge, Button, useToast,
  FormControl, FormLabel,
} from '@chakra-ui/react';
import { ExternalLinkIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { enableJabaki, disableJabaki, JabakiStatus } from '../../../services/domainApi';
import { setSlug, validateSlug } from '../../../services/landingPageApi';

interface JabakiSubdomainProps {
  jabaki: JabakiStatus;
  onUpdate: () => void;
}

export default function JabakiSubdomain({ jabaki, onUpdate }: JabakiSubdomainProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();
  const [toggling, setToggling] = useState(false);

  // Slug editing state
  const [editingSlug, setEditingSlug] = useState(false);
  const [slugInput, setSlugInput] = useState('');
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugSaving, setSlugSaving] = useState(false);
  const [slugRenameConfirm, setSlugRenameConfirm] = useState(false);

  // Extract current slug from domain (e.g. "peter.jabaki.nl" → "peter")
  const currentSlug = jabaki.domain ? jabaki.domain.replace('.jabaki.nl', '') : null;

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
        setEditingSlug(false);
        setSlugRenameConfirm(false);
        toast({
          title: resp.renamed_from
            ? (t('landingPage.editor.slugRenamed') || 'URL renamed')
            : (t('landingPage.slug.saved') || 'Slug saved'),
          description: resp.renamed_from ? `${resp.renamed_from} → ${slugInput}` : undefined,
          status: 'success',
          duration: 4000,
        });
        if (resp.warnings && resp.warnings.length > 0) {
          toast({ title: t('landingPage.editor.slugRenameWarnings'), description: resp.warnings.join(', '), status: 'warning', duration: 8000 });
        }
        onUpdate();
      } else {
        setSlugError(resp.error || 'Failed to save slug');
      }
    } catch (err) {
      setSlugError(err instanceof Error ? err.message : 'Failed to save slug');
    } finally {
      setSlugSaving(false);
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
                {!editingSlug ? (
                  <>
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
                    <Button
                      size="xs"
                      variant="ghost"
                      colorScheme="orange"
                      onClick={() => { setSlugInput(currentSlug || ''); setEditingSlug(true); setSlugError(null); setSlugRenameConfirm(false); }}
                    >
                      {t('landingPage.editor.changeSlug')}
                    </Button>
                  </>
                ) : (
                  <VStack spacing={2} align="stretch" w="100%">
                    <HStack spacing={1}>
                      <Box
                        as="input"
                        w="160px"
                        px={2}
                        py={1}
                        bg="gray.700"
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
                      <Text color="gray.500" fontSize="xs">.jabaki.nl</Text>
                    </HStack>
                    {slugRenameConfirm && (
                      <Text color="yellow.300" fontSize="xs">
                        {t('landingPage.editor.slugRenameWarning')}
                      </Text>
                    )}
                    {slugError && <Text color="red.300" fontSize="xs">{slugError}</Text>}
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
                  </VStack>
                )}
              </HStack>
            )}
          </>
        )}
      </VStack>
    </Box>
  );
}
