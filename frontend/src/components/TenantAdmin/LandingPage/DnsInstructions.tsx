/**
 * DnsInstructions — Context-aware DNS guidance for custom domain setup.
 *
 * Shows different instructions for:
 * - Subdomain (www.x.nl): CNAME record
 * - Root domain (x.nl): ALIAS/ANAME or redirect guidance
 *
 * Includes copy buttons for record values.
 *
 * Task 5.4
 */

import React from 'react';
import {
  Box, VStack, HStack, Text, Code, Alert, AlertIcon, IconButton,
  useToast, Table, Thead, Tbody, Tr, Th, Td, TableContainer,
} from '@chakra-ui/react';
import { CopyIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { DnsInstructions as DnsInstructionsType } from '../../../services/domainApi';

interface DnsInstructionsProps {
  domain: string;
  instructions: DnsInstructionsType;
}

export default function DnsInstructions({ domain, instructions }: DnsInstructionsProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const isRootDomain = !domain.startsWith('www.') && domain.split('.').length === 2;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({
      title: t('landingPage.domains.copied') || 'Copied!',
      status: 'success',
      duration: 1500,
      isClosable: true,
    });
  };

  return (
    <VStack spacing={4} align="stretch">
      <Text color="white" fontWeight="bold" fontSize="sm">
        {t('landingPage.domains.dnsTitle') || 'DNS Configuration'}
      </Text>

      <Alert status="info" bg="blue.900" borderRadius="md" fontSize="xs">
        <AlertIcon />
        <Text color="gray.200">
          {t('landingPage.domains.dnsExplanation') || 'Add the following DNS records at your domain registrar. Verification typically takes 5–30 minutes after records are added.'}
        </Text>
      </Alert>

      {/* DNS Records Table */}
      <TableContainer>
        <Table size="sm" variant="simple">
          <Thead>
            <Tr>
              <Th color="gray.400" borderColor="gray.600">
                {t('landingPage.domains.dnsType') || 'Type'}
              </Th>
              <Th color="gray.400" borderColor="gray.600">
                {t('landingPage.domains.dnsName') || 'Name'}
              </Th>
              <Th color="gray.400" borderColor="gray.600">
                {t('landingPage.domains.dnsValue') || 'Value'}
              </Th>
            </Tr>
          </Thead>
          <Tbody>
            {instructions.records.map((record, idx) => (
              <Tr key={idx}>
                <Td borderColor="gray.700">
                  <Code colorScheme="orange" fontSize="xs">CNAME</Code>
                </Td>
                <Td borderColor="gray.700">
                  <HStack spacing={1}>
                    <Code fontSize="xs" bg="gray.700" color="gray.200" px={2} maxW="200px" isTruncated>
                      {record.name}
                    </Code>
                    <IconButton
                      aria-label="Copy name"
                      icon={<CopyIcon />}
                      size="xs"
                      variant="ghost"
                      colorScheme="orange"
                      onClick={() => copyToClipboard(record.name)}
                    />
                  </HStack>
                </Td>
                <Td borderColor="gray.700">
                  <HStack spacing={1}>
                    <Code fontSize="xs" bg="gray.700" color="gray.200" px={2} maxW="200px" isTruncated>
                      {record.value}
                    </Code>
                    <IconButton
                      aria-label="Copy value"
                      icon={<CopyIcon />}
                      size="xs"
                      variant="ghost"
                      colorScheme="orange"
                      onClick={() => copyToClipboard(record.value)}
                    />
                  </HStack>
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </TableContainer>

      {/* Help reference to full documentation */}
      <Box>
        <Text color="gray.400" fontSize="xs" fontStyle="italic">
          {t('landingPage.domains.docsReference') || 'For detailed instructions, see the Domain Setup Guide in the user manual (Landing Page → Connecting Your Own Domain).'}
        </Text>
      </Box>

      {isRootDomain ? (
        <Box bg="yellow.900" p={3} borderRadius="md" border="1px solid" borderColor="yellow.700">
          <VStack spacing={2} align="stretch">
            <Text color="yellow.200" fontSize="xs" fontWeight="bold">
              {t('landingPage.domains.rootDomainNote') || '⚠ Root domain detected'}
            </Text>
            <Text color="gray.300" fontSize="xs">
              {t('landingPage.domains.rootDomainExplanation') || 'Root domains (e.g., example.nl without www) cannot use CNAME records. You need an ALIAS or ANAME record, which is only supported by some DNS providers.'}
            </Text>
            <Text color="gray.300" fontSize="xs" fontWeight="bold" mt={1}>
              {t('landingPage.domains.aliasSupported') || 'Providers that support ALIAS/ANAME:'}
            </Text>
            <Text color="gray.400" fontSize="xs">
              Route 53, Cloudflare, DNSimple, NS1, Constellix
            </Text>
            <Text color="gray.300" fontSize="xs" fontWeight="bold" mt={1}>
              {t('landingPage.domains.aliasNotSupported') || 'Providers without ALIAS support:'}
            </Text>
            <Text color="gray.400" fontSize="xs">
              TransIP (basic), Hostnet, Antagonist
            </Text>
            <Text color="gray.300" fontSize="xs" mt={1}>
              {t('landingPage.domains.rootDomainWorkaround') || 'Alternative: use www.yourdomain.nl (CNAME) and set up a redirect from the root to www at your registrar.'}
            </Text>
          </VStack>
        </Box>
      ) : (
        <Box bg="gray.750" p={3} borderRadius="md" border="1px solid" borderColor="gray.600">
          <HStack spacing={2}>
            <Text color="green.300" fontSize="xs">✓</Text>
            <Text color="gray.300" fontSize="xs">
              {t('landingPage.domains.subdomainNote') || 'Subdomain detected — CNAME records work with all DNS providers.'}
            </Text>
          </HStack>
        </Box>
      )}
    </VStack>
  );
}
