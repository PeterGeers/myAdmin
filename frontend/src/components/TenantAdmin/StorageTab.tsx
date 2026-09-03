/**
 * Storage Tab - Provider-driven storage configuration
 *
 * Consolidates: provider selection + credentials + folder config
 * Replaces: Credentials, Configuration, Settings tabs for storage
 *
 * Flow: Pick provider → configure that provider → folder mappings
 *
 * Logic (data loading, save/upload/OAuth handlers) lives in useStorageTab;
 * this file is the render layer only.
 */

import {
  Box, VStack, HStack, Text, Spinner, Badge,
  FormControl, FormLabel, Select, Input, Button,
  SimpleGrid, Alert, AlertIcon,
  Accordion, AccordionItem, AccordionButton, AccordionPanel, AccordionIcon,
  Table, Thead, Tbody, Tr, Th, Td,
} from '@chakra-ui/react';
import { ExternalLinkIcon, RepeatIcon, CheckCircleIcon, AttachmentIcon } from '@chakra-ui/icons';
import { FiFolder } from 'react-icons/fi';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { AssetPicker } from '../common/AssetPicker/AssetPicker';
import { useStorageTab } from './useStorageTab';

interface StorageTabProps {
  tenant: string;
}

export default function StorageTab({ tenant }: StorageTabProps) {
  const { t } = useTypedTranslation('admin');
  const {
    provider, setProvider, providerLoading, providerSaving, providerOptions,
    credentials, credsLoading, loadCredentials,
    folderConfig,
    gdFolderId, setGdFolderId,
    logoUploading, logoS3Key, logoInputRef,
    isLogoPickerOpen, onLogoPickerOpen, onLogoPickerClose, handleLogoAssetSelect,
    handleProviderSave, handleGdFolderSave, handleLogoUpload,
    handleStartOAuth, handleFileUpload, handleTestConnection,
    formatDate, hasGdCreds,
  } = useStorageTab(tenant);

  if (providerLoading) {
    return <Box p={4}><Spinner color="orange.400" /><Text color="gray.400" ml={2} display="inline">Loading storage settings...</Text></Box>;
  }

  return (
    <Box>
      <Accordion allowMultiple defaultIndex={[0, 1, 2]}>
        {/* Provider Selection */}
        <AccordionItem border="none" mb={4}>
          <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
            <Box flex="1" textAlign="left">
              <Text color="white" fontWeight="bold">{t('tenantAdmin.tabs.storage')} Provider</Text>
            </Box>
            <AccordionIcon color="gray.400" />
          </AccordionButton>
          <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl>
                <FormLabel color="gray.300">Storage Provider</FormLabel>
                <Select value={provider} onChange={e => setProvider(e.target.value)}
                  bg="gray.700" color="white" borderColor="gray.600">
                  {providerOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormControl>
              <FormControl display="flex" alignItems="flex-end">
                <Button colorScheme="orange" onClick={handleProviderSave}
                  isLoading={providerSaving} size="sm">
                  Save Provider
                </Button>
              </FormControl>
            </SimpleGrid>
          </AccordionPanel>
        </AccordionItem>

        {/* Google Drive Configuration */}
        {provider === 'google_drive' && (
          <AccordionItem border="none" mb={4}>
            <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
              <Box flex="1" textAlign="left">
                <Text color="white" fontWeight="bold">Google Drive Configuration</Text>
              </Box>
              <AccordionIcon color="gray.400" />
            </AccordionButton>
            <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
              <VStack spacing={6} align="stretch">
                {/* Credentials status */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>Credentials</Text>
                  {credsLoading ? <Spinner size="sm" color="orange.400" /> : hasGdCreds ? (
                    <VStack spacing={2} align="stretch">
                      <Table size="sm" variant="simple">
                        <Thead><Tr>
                          <Th color="gray.400">Type</Th>
                          <Th color="gray.400">Updated</Th>
                          <Th color="gray.400">Status</Th>
                        </Tr></Thead>
                        <Tbody>
                          {credentials.filter(c => c.type.startsWith('google_drive')).map(c => (
                            <Tr key={c.type}>
                              <Td color="gray.300"><Badge colorScheme="blue">{c.type}</Badge></Td>
                              <Td color="gray.400" fontSize="sm">{formatDate(c.updated_at)}</Td>
                              <Td><Badge colorScheme="green"><CheckCircleIcon mr={1} />OK</Badge></Td>
                            </Tr>
                          ))}
                        </Tbody>
                      </Table>
                      <HStack>
                        <Button size="xs" variant="outline" colorScheme="orange" onClick={handleTestConnection}>
                          Test Connection
                        </Button>
                        <Button size="xs" variant="outline" colorScheme="blue" onClick={loadCredentials}
                          leftIcon={<RepeatIcon />}>Refresh</Button>
                      </HStack>
                    </VStack>
                  ) : (
                    <Alert status="warning" bg="yellow.900" borderRadius="md" mb={2}>
                      <AlertIcon /><Text color="gray.100" fontSize="sm">No Google Drive credentials configured.</Text>
                    </Alert>
                  )}
                </Box>

                {/* Upload + OAuth */}
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                  <Box p={4} bg="gray.700" borderRadius="md">
                    <Text color="gray.300" fontWeight="bold" mb={2}>Upload Credentials JSON</Text>
                    <Input type="file" accept=".json" onChange={handleFileUpload}
                      bg="gray.600" color="white" borderColor="gray.500" p={1} size="sm" />
                  </Box>
                  <Box p={4} bg="gray.700" borderRadius="md">
                    <Text color="gray.300" fontWeight="bold" mb={2}>OAuth Authentication</Text>
                    <Button leftIcon={<ExternalLinkIcon />} onClick={handleStartOAuth}
                      colorScheme="blue" size="sm">
                      Start Google Drive OAuth
                    </Button>
                  </Box>
                </SimpleGrid>

                {/* Folder ID */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>Root Folder ID</Text>
                  <HStack>
                    <Input value={gdFolderId} onChange={e => setGdFolderId(e.target.value)}
                      placeholder="Google Drive folder ID" bg="gray.700" color="white"
                      borderColor="gray.600" />
                    <Button colorScheme="orange" size="sm" onClick={handleGdFolderSave}
                      isLoading={providerSaving}>Save</Button>
                  </HStack>
                </Box>

                {/* Folder mappings from tenant_config */}
                {Object.keys(folderConfig).length > 0 && (
                  <Box>
                    <Text color="gray.300" fontWeight="bold" mb={2}>Configured Folders</Text>
                    <Table size="sm" variant="simple">
                      <Thead><Tr>
                        <Th color="gray.400">Folder</Th>
                        <Th color="gray.400">ID</Th>
                      </Tr></Thead>
                      <Tbody>
                        {Object.entries(folderConfig).map(([key, val]) => (
                          <Tr key={key}>
                            <Td color="gray.300" fontSize="sm">{key.replace('google_drive_', '').replace('_folder_id', '').replace(/_/g, ' ')}</Td>
                            <Td color="gray.400" fontSize="xs" fontFamily="mono">{val}</Td>
                          </Tr>
                        ))}
                      </Tbody>
                    </Table>
                  </Box>
                )}
              </VStack>
            </AccordionPanel>
          </AccordionItem>
        )}

        {provider === 's3_shared' && (
          <AccordionItem border="none" mb={4}>
            <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
              <Box flex="1" textAlign="left">
                <Text color="white" fontWeight="bold">S3 Shared Bucket</Text>
              </Box>
              <AccordionIcon color="gray.400" />
            </AccordionButton>
            <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
              <Alert status="info" bg="blue.900" borderRadius="md">
                <AlertIcon />
                <Text color="gray.100" fontSize="sm">
                  S3 shared bucket is configured at the platform level. No tenant-specific configuration needed.
                </Text>
              </Alert>
            </AccordionPanel>
          </AccordionItem>
        )}

        {provider === 's3_tenant' && (
          <AccordionItem border="none" mb={4}>
            <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
              <Box flex="1" textAlign="left">
                <Text color="white" fontWeight="bold">S3 Tenant Bucket</Text>
              </Box>
              <AccordionIcon color="gray.400" />
            </AccordionButton>
            <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
              <Alert status="info" bg="blue.900" borderRadius="md">
                <AlertIcon />
                <Text color="gray.100" fontSize="sm">
                  S3 tenant bucket configuration — bucket name and cross-account credentials can be set in the Advanced tab.
                </Text>
              </Alert>
            </AccordionPanel>
          </AccordionItem>
        )}

        {/* Branding / Logo Upload — shown for S3 tenants */}
        {(provider === 's3_shared' || provider === 's3_tenant') && (
          <AccordionItem border="none" mb={4}>
            <AccordionButton bg="gray.700" borderRadius="md" _hover={{ bg: 'gray.600' }}>
              <Box flex="1" textAlign="left">
                <Text color="white" fontWeight="bold">Branding — Company Logo</Text>
              </Box>
              <AccordionIcon color="gray.400" />
            </AccordionButton>
            <AccordionPanel bg="gray.800" borderRadius="md" mt={1} p={4}>
              <VStack spacing={4} align="stretch">
                <Text color="gray.300" fontSize="sm">
                  Upload your company logo (PNG, JPG, or SVG, max 2MB). This logo will be used on generated invoices.
                </Text>
                <FormControl>
                  <FormLabel color="gray.300">Logo File</FormLabel>
                  <Input
                    ref={logoInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/svg+xml"
                    onChange={handleLogoUpload}
                    bg="gray.700"
                    color="white"
                    borderColor="gray.600"
                    p={1}
                    size="sm"
                    disabled={logoUploading}
                  />
                </FormControl>
                {/* Choose existing asset for logo */}
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="orange"
                  leftIcon={<FiFolder />}
                  onClick={onLogoPickerOpen}
                  isDisabled={logoUploading}
                  data-testid="logo-choose-existing-btn"
                >
                  or choose existing
                </Button>
                {logoUploading && (
                  <HStack>
                    <Spinner size="sm" color="orange.400" />
                    <Text color="gray.400" fontSize="sm">Uploading...</Text>
                  </HStack>
                )}
                {logoS3Key && (
                  <HStack>
                    <AttachmentIcon color="green.400" />
                    <Text color="gray.300" fontSize="sm">
                      Current logo: <Text as="span" fontFamily="mono" fontSize="xs" color="gray.400">{logoS3Key}</Text>
                    </Text>
                  </HStack>
                )}
              </VStack>
              {/* Asset Picker for logo selection */}
              <AssetPicker
                isOpen={isLogoPickerOpen}
                onClose={onLogoPickerClose}
                onSelect={handleLogoAssetSelect}
                defaultCategory="branding"
                defaultMediaType=""
                allowedMediaTypes={['image']}
              />
            </AccordionPanel>
          </AccordionItem>
        )}
      </Accordion>
    </Box>
  );
}
