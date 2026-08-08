/**
 * CustomDomainForm — Register, verify, and remove custom domain.
 *
 * Handles the full custom domain lifecycle:
 * - Input + register
 * - Show DNS instructions after registration
 * - Verify button (when pending/validating)
 * - Remove with confirmation
 * - Status badge display
 *
 * Tasks 5.3, 5.5
 */

import React, { useState } from 'react';
import {
  Box, VStack, HStack, Text, Input, Button, Badge, useToast,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter,
  useDisclosure, Link,
} from '@chakra-ui/react';
import { ExternalLinkIcon, DeleteIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  registerCustomDomain, verifyCustomDomain, removeCustomDomain,
  CustomDomainStatus,
} from '../../../services/domainApi';
import DnsInstructions from './DnsInstructions';

interface CustomDomainFormProps {
  custom: CustomDomainStatus;
  onUpdate: () => void;
}

// ============================================================================
// Status Badge Component (Task 5.5)
// ============================================================================

function DomainStatusBadge({ status }: { status: string | null }) {
  const { t } = useTypedTranslation('admin');

  if (!status) return null;

  const config: Record<string, { colorScheme: string; label: string }> = {
    pending_dns: {
      colorScheme: 'gray',
      label: t('landingPage.domains.statusPending') || 'Pending DNS',
    },
    validating: {
      colorScheme: 'yellow',
      label: t('landingPage.domains.statusValidating') || 'Validating',
    },
    issued: {
      colorScheme: 'green',
      label: t('landingPage.domains.statusActive') || 'Active',
    },
    failed: {
      colorScheme: 'red',
      label: t('landingPage.domains.statusFailed') || 'Failed',
    },
    revoked: {
      colorScheme: 'red',
      label: t('landingPage.domains.statusRevoked') || 'Revoked',
    },
  };

  const badgeConfig = config[status] || { colorScheme: 'gray', label: status };

  return (
    <Badge colorScheme={badgeConfig.colorScheme} fontSize="xs">
      {badgeConfig.label}
    </Badge>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function CustomDomainForm({ custom, onUpdate }: CustomDomainFormProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const [domainInput, setDomainInput] = useState('');
  const [registering, setRegistering] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);

  const hasDomain = !!custom.domain;
  const isPending = custom.status === 'pending_dns' || custom.status === 'validating';
  const isActive = custom.is_active;

  // Client-side domain validation
  const validateDomain = (domain: string): string | null => {
    if (!domain) return t('landingPage.domains.domainRequired') || 'Domain is required';
    if (domain.includes(' ')) return t('landingPage.domains.domainNoSpaces') || 'Domain cannot contain spaces';
    if (!domain.includes('.')) return t('landingPage.domains.domainNeedsDot') || 'Must include a TLD (e.g., .nl, .com)';
    if (domain.endsWith('.jabaki.nl')) return t('landingPage.domains.domainNoJabaki') || 'Cannot use jabaki.nl subdomains';
    const domainRegex = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$/;
    if (!domainRegex.test(domain)) return t('landingPage.domains.domainInvalid') || 'Invalid domain format';
    return null;
  };

  const handleRegister = async () => {
    const domain = domainInput.trim().toLowerCase();
    const error = validateDomain(domain);
    if (error) {
      setInputError(error);
      return;
    }

    setRegistering(true);
    setInputError(null);
    try {
      const result = await registerCustomDomain(domain);
      if (result.success) {
        toast({
          title: t('landingPage.domains.registered') || 'Domain registered',
          description: t('landingPage.domains.addDnsRecords') || 'Add the DNS records below to verify ownership.',
          status: 'success',
          duration: 5000,
        });
        setDomainInput('');
        onUpdate();
      } else {
        setInputError(result.error || 'Registration failed');
      }
    } catch (err) {
      setInputError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setRegistering(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const result = await verifyCustomDomain();
      if (result.success) {
        toast({
          title: result.data.is_active
            ? (t('landingPage.domains.verified') || 'Domain verified!')
            : (t('landingPage.domains.verifyInProgress') || 'Verification in progress'),
          description: result.data.message,
          status: result.data.is_active ? 'success' : 'info',
          duration: 5000,
        });
        onUpdate();
      } else {
        toast({
          title: t('landingPage.domains.verifyError') || 'Verification failed',
          description: result.error,
          status: 'error',
          duration: 5000,
        });
      }
    } catch (err) {
      toast({
        title: t('landingPage.domains.verifyError') || 'Verification failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    try {
      await removeCustomDomain();
      toast({
        title: t('landingPage.domains.removed') || 'Domain removed',
        status: 'info',
        duration: 3000,
      });
      onClose();
      onUpdate();
    } catch (err) {
      toast({
        title: t('landingPage.domains.removeError') || 'Remove failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setRemoving(false);
    }
  };

  return (
    <Box bg="gray.800" p={4} borderRadius="md" border="1px solid" borderColor="gray.700">
      <VStack spacing={4} align="stretch">
        <HStack justify="space-between">
          <Text color="white" fontWeight="bold" fontSize="sm">
            {t('landingPage.domains.customTitle') || 'Custom Domain'}
          </Text>
          {hasDomain && <DomainStatusBadge status={custom.status} />}
        </HStack>

        <Text color="gray.400" fontSize="xs">
          {t('landingPage.domains.customDescription') || 'Connect your own domain for a fully branded experience.'}
        </Text>

        {/* Active domain display */}
        {hasDomain && isActive && (
          <HStack justify="space-between" bg="green.900" p={3} borderRadius="md">
            <HStack spacing={2}>
              <Text color="green.200" fontSize="sm">✓</Text>
              <Link
                href={`https://${custom.domain}`}
                isExternal
                color="green.200"
                fontSize="sm"
                fontFamily="mono"
              >
                {custom.domain} <ExternalLinkIcon mx="2px" />
              </Link>
            </HStack>
            <Button
              size="xs"
              colorScheme="red"
              variant="ghost"
              leftIcon={<DeleteIcon />}
              onClick={onOpen}
            >
              {t('landingPage.domains.remove') || 'Remove'}
            </Button>
          </HStack>
        )}

        {/* Pending domain with DNS instructions */}
        {hasDomain && isPending && (
          <VStack spacing={3} align="stretch">
            <HStack justify="space-between" bg="gray.750" p={3} borderRadius="md" border="1px solid" borderColor="gray.600">
              <Text color="gray.200" fontSize="sm" fontFamily="mono">
                {custom.domain}
              </Text>
              <HStack spacing={2}>
                <Button
                  size="xs"
                  colorScheme="orange"
                  onClick={handleVerify}
                  isLoading={verifying}
                >
                  {t('landingPage.domains.verify') || 'Verify'}
                </Button>
                <Button
                  size="xs"
                  colorScheme="red"
                  variant="ghost"
                  leftIcon={<DeleteIcon />}
                  onClick={onOpen}
                >
                  {t('landingPage.domains.remove') || 'Remove'}
                </Button>
              </HStack>
            </HStack>

            {custom.dns_instructions && (
              <DnsInstructions
                domain={custom.domain!}
                instructions={custom.dns_instructions}
              />
            )}
          </VStack>
        )}

        {/* Failed domain */}
        {hasDomain && custom.status === 'failed' && (
          <VStack spacing={2} align="stretch">
            <HStack justify="space-between" bg="red.900" p={3} borderRadius="md">
              <Text color="red.200" fontSize="sm" fontFamily="mono">
                {custom.domain}
              </Text>
              <HStack spacing={2}>
                <Button
                  size="xs"
                  colorScheme="orange"
                  onClick={handleVerify}
                  isLoading={verifying}
                >
                  {t('landingPage.domains.retryVerify') || 'Retry'}
                </Button>
                <Button
                  size="xs"
                  colorScheme="red"
                  variant="ghost"
                  leftIcon={<DeleteIcon />}
                  onClick={onOpen}
                >
                  {t('landingPage.domains.remove') || 'Remove'}
                </Button>
              </HStack>
            </HStack>
            <Text color="red.300" fontSize="xs">
              {t('landingPage.domains.failedExplanation') || 'DNS verification failed. Check your DNS records and try again.'}
            </Text>
          </VStack>
        )}

        {/* Registration form (only when no domain is registered) */}
        {!hasDomain && (
          <VStack spacing={3} align="stretch">
            <HStack>
              <Input
                size="sm"
                bg="gray.700"
                color="white"
                borderColor={inputError ? 'red.400' : 'gray.600'}
                placeholder="www.your-domain.nl"
                _placeholder={{ color: 'gray.500' }}
                value={domainInput}
                onChange={(e) => {
                  setDomainInput(e.target.value.toLowerCase().replace(/[^a-z0-9.-]/g, ''));
                  setInputError(null);
                }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleRegister(); }}
              />
              <Button
                size="sm"
                colorScheme="orange"
                onClick={handleRegister}
                isLoading={registering}
                isDisabled={!domainInput.trim()}
              >
                {t('landingPage.domains.register') || 'Register'}
              </Button>
            </HStack>
            {inputError && (
              <Text color="red.300" fontSize="xs">{inputError}</Text>
            )}
          </VStack>
        )}
      </VStack>

      {/* Remove Confirmation Modal */}
      <Modal isOpen={isOpen} onClose={onClose} isCentered size="sm">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader fontSize="md">
            {t('landingPage.domains.removeConfirmTitle') || 'Remove Custom Domain'}
          </ModalHeader>
          <ModalBody>
            <Text fontSize="sm" color="gray.300">
              {t('landingPage.domains.removeConfirmMessage') || 'Are you sure you want to remove this domain? The SSL certificate will be deleted and visitors will no longer be able to reach your page via this domain.'}
            </Text>
            {custom.domain && (
              <Text fontFamily="mono" fontSize="sm" color="orange.300" mt={2}>
                {custom.domain}
              </Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button size="sm" variant="ghost" mr={3} onClick={onClose}>
              {t('landingPage.domains.cancel') || 'Cancel'}
            </Button>
            <Button
              size="sm"
              colorScheme="red"
              onClick={handleRemove}
              isLoading={removing}
            >
              {t('landingPage.domains.confirmRemove') || 'Remove Domain'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}
