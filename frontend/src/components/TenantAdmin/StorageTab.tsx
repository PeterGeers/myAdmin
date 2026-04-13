/**
 * Storage Tab - Provider-driven storage configuration
 * 
 * Consolidates: provider selection + credentials + folder config
 * Replaces: Credentials, Configuration, Settings tabs for storage
 * 
 * Flow: Pick provider → configure that provider → folder mappings
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Text, Spinner, useToast, Badge,
  FormControl, FormLabel, Select, Input, Button,
  SimpleGrid, Alert, AlertIcon,
  Accordion, AccordionItem, AccordionButton, AccordionPanel, AccordionIcon,
  Table, Thead, Tbody, Tr, Th, Td,
} from '@chakra-ui/react';
import { ExternalLinkIcon, RepeatIcon, CheckCircleIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { getParameterSchema } from '../../services/parameterSchemaService';
import { createParameter } from '../../services/parameterService';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

interface CredentialInfo {
  type: string;
  created_at: string | null;
  updated_at: string | null;
}

interface FolderConfig {
  [key: string]: string;
}

interface StorageTabProps {
  tenant: string;
}

export default function StorageTab({ tenant }: StorageTabProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  // Provider state
  const [provider, setProvider] = useState('');
  const [providerLoading, setProviderLoading] = useState(true);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerOptions, setProviderOptions] = useState<{value: string; label: string}[]>([]);

  // Credentials state
  const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
  const [credsLoading, setCredsLoading] = useState(false);

  // Folder config state
  const [folderConfig, setFolderConfig] = useState<FolderConfig>({});
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [foldersLoading, setFoldersLoading] = useState(false);

  // Google Drive specific
  const [gdFolderId, setGdFolderId] = useState('');

  const getToken = async () => {
    const session = await fetchAuthSession();
    return session.tokens?.idToken?.toString() || '';
  };

  const authHeaders = async () => {
    const token = await getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'X-Tenant': tenant,
      'Content-Type': 'application/json',
    };
  };

  // Load provider from parameter schema
  const loadProvider = useCallback(async () => {
    setProviderLoading(true);
    try {
      const data = await getParameterSchema();
      const storageSection = data.schema?.storage;
      if (storageSection?.params?.invoice_provider) {
        const def = storageSection.params.invoice_provider;
        setProviderOptions(def.options || []);
        const current = def.current_value ?? def.default ?? '';
        setProvider(String(current));

        // Also grab google_drive_folder_id if present
        const gdFolder = storageSection.params.google_drive_folder_id;
        if (gdFolder?.current_value) {
          setGdFolderId(String(gdFolder.current_value));
        }
      }
    } catch (e: any) {
      toast({ title: 'Failed to load storage settings', description: e.message, status: 'error', duration: 5000 });
    } finally {
      setProviderLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]);

  // Load credentials
  const loadCredentials = useCallback(async () => {
    setCredsLoading(true);
    try {
      const token = await getToken();
      const resp = await fetch(`${API_URL}/api/tenant-admin/credentials`, {
        headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant': tenant },
      });
      if (resp.ok) {
        const data = await resp.json();
        setCredentials(data.credentials || []);
      }
    } catch { /* ignore */ }
    finally { setCredsLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  // Load folder config
  const loadFolderConfig = useCallback(async () => {
    setFoldersLoading(true);
    try {
      const token = await getToken();
      const resp = await fetch(`${API_URL}/api/tenant-admin/storage/config`, {
        headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant': tenant },
      });
      if (resp.ok) {
        const data = await resp.json();
        setFolderConfig(data.config || {});
      }
    } catch { /* ignore */ }
    finally { setFoldersLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  useEffect(() => {
    loadProvider();
    loadCredentials();
    loadFolderConfig();
  }, [loadProvider, loadCredentials, loadFolderConfig]);

  // Save provider selection
  const handleProviderSave = async () => {
    setProviderSaving(true);
    try {
      const res = await createParameter({
        scope: 'tenant', namespace: 'storage', key: 'invoice_provider',
        value: provider, value_type: 'string', is_secret: false,
      });
      if (res.success) {
        toast({ title: 'Provider saved', status: 'success', duration: 2000 });
        await loadProvider();
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: 'Save failed', description: e.message, status: 'error', duration: 5000 });
    } finally { setProviderSaving(false); }
  };

  // Save Google Drive folder ID
  const handleGdFolderSave = async () => {
    setProviderSaving(true);
    try {
      const res = await createParameter({
        scope: 'tenant', namespace: 'storage', key: 'google_drive_folder_id',
        value: gdFolderId, value_type: 'string', is_secret: false,
      });
      if (res.success) {
        toast({ title: 'Folder ID saved', status: 'success', duration: 2000 });
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: 'Save failed', description: e.message, status: 'error', duration: 5000 });
    } finally { setProviderSaving(false); }
  };

  // Start Google Drive OAuth
  const handleStartOAuth = async () => {
    try {
      const headers = await authHeaders();
      const resp = await fetch(`${API_URL}/api/tenant-admin/credentials/oauth/start`, {
        method: 'POST', headers,
        body: JSON.stringify({ service: 'google_drive' }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || 'Failed to start OAuth');
      }
      const data = await resp.json();

      const messageHandler = async (event: MessageEvent) => {
        if (event.data.type === 'oauth_success') {
          window.removeEventListener('message', messageHandler);
          try {
            const completeResp = await fetch(`${API_URL}/api/tenant-admin/credentials/oauth/complete`, {
              method: 'POST', headers,
              body: JSON.stringify({ code: event.data.code, state: event.data.state, service: 'google_drive' }),
            });
            if (completeResp.ok) {
              toast({ title: 'Google Drive connected', status: 'success', duration: 5000 });
              loadCredentials();
            }
          } catch (e: any) {
            toast({ title: 'OAuth failed', description: e.message, status: 'error', duration: 5000 });
          }
        } else if (event.data.type === 'oauth_error') {
          window.removeEventListener('message', messageHandler);
          toast({ title: 'OAuth failed', description: event.data.error, status: 'error', duration: 5000 });
        }
      };
      window.addEventListener('message', messageHandler);

      const popup = window.open(data.oauth_url, '_blank', 'width=600,height=700');
      if (!popup) {
        window.removeEventListener('message', messageHandler);
        toast({ title: 'Popup blocked', description: 'Please allow popups', status: 'warning', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: 'OAuth failed', description: e.message, status: 'error', duration: 5000 });
    }
  };

  // Upload credentials file
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !file.name.endsWith('.json')) {
      toast({ title: 'Please select a JSON file', status: 'warning', duration: 3000 });
      return;
    }
    try {
      const token = await getToken();
      const formData = new FormData();
      formData.append('file', file);
      formData.append('credential_type', 'google_drive');
      const resp = await fetch(`${API_URL}/api/tenant-admin/credentials`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant': tenant },
        body: formData,
      });
      if (resp.ok) {
        toast({ title: 'Credentials uploaded', status: 'success', duration: 3000 });
        loadCredentials();
      } else {
        const err = await resp.json();
        throw new Error(err.error || 'Upload failed');
      }
    } catch (e: any) {
      toast({ title: 'Upload failed', description: e.message, status: 'error', duration: 5000 });
    }
    event.target.value = '';
  };

  // Test credential connection
  const handleTestConnection = async () => {
    try {
      const headers = await authHeaders();
      const resp = await fetch(`${API_URL}/api/tenant-admin/credentials/test`, {
        method: 'POST', headers,
        body: JSON.stringify({ credential_type: 'google_drive_credentials' }),
      });
      const data = await resp.json();
      const result = data.test_result;
      toast({
        title: result?.success ? 'Connection OK' : 'Connection failed',
        description: result?.message,
        status: result?.success ? 'success' : 'error',
        duration: 5000,
      });
    } catch (e: any) {
      toast({ title: 'Test failed', description: e.message, status: 'error', duration: 5000 });
    }
  };

  const formatDate = (d: string | null) => d ? new Date(d).toLocaleString() : 'N/A';
  const hasGdCreds = credentials.some(c => c.type.startsWith('google_drive'));

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
      </Accordion>
    </Box>
  );
}
