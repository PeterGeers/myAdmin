/**
 * Storage Configuration Component
 * 
 * Allows Tenant_Admin to configure Google Drive folder mappings for storage.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, useToast, Spinner,
  FormControl, FormLabel, Select, Divider,
  Table, Thead, Tbody, Tr, Th, Td, Badge, Card, CardHeader,
  CardBody, Heading, SimpleGrid, Stat, StatLabel, StatNumber,
  StatHelpText, Alert, AlertIcon
} from '@chakra-ui/react';
import {
  browseFolders,
  getStorageConfig,
  updateStorageConfig,
  testFolder,
  getStorageUsage,
  StorageFolder,
  StorageConfig,
  StorageUsage
} from '../../services/tenantAdminApi';

interface StorageConfigurationProps {
  tenant: string;
}

export default function StorageConfiguration({ tenant }: StorageConfigurationProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [folders, setFolders] = useState<StorageFolder[]>([]);
  const [config, setConfig] = useState<StorageConfig>({});
  const [usage, setUsage] = useState<StorageUsage>({});
  const [testResults, setTestResults] = useState<{ [key: string]: any }>({});
  
  const toast = useToast();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Load folders, config, and usage in parallel
      const [foldersRes, configRes, usageRes] = await Promise.all([
        browseFolders(),
        getStorageConfig(),
        getStorageUsage().catch(() => ({ usage: {} })) // Optional
      ]);

      setFolders(foldersRes.folders || []);
      setConfig(configRes.config || {});
      setUsage(usageRes.usage || {});
    } catch (error: any) {
      toast({
        title: 'Failed to load storage data',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSelectFolder = (folderType: string, folderId: string) => {
    setConfig(prev => ({
      ...prev,
      [`${folderType}_folder_id`]: folderId
    }));
  };

  const handleTestFolder = async (folderType: string) => {
    const folderId = config[`${folderType}_folder_id` as keyof StorageConfig];
    
    if (!folderId) {
      toast({
        title: 'No folder selected',
        description: `Please select a folder for ${folderType}`,
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setTesting(folderType);
    try {
      const result = await testFolder(folderId);
      
      setTestResults(prev => ({
        ...prev,
        [folderType]: result.test_result
      }));

      if (result.test_result.accessible) {
        toast({
          title: 'Folder accessible',
          description: `${folderType} folder has read and write access`,
          status: 'success',
          duration: 3000,
        });
      } else {
        toast({
          title: 'Folder not accessible',
          description: result.test_result.read_error || result.test_result.write_error || 'Access denied',
          status: 'error',
          duration: 5000,
        });
      }
    } catch (error: any) {
      toast({
        title: 'Test failed',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setTesting(null);
    }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      await updateStorageConfig(config, false);
      
      toast({
        title: 'Configuration saved',
        description: 'Storage configuration updated successfully',
        status: 'success',
        duration: 3000,
      });

      // Reload usage after save
      const usageRes = await getStorageUsage().catch(() => ({ usage: {} }));
      setUsage(usageRes.usage || {});
    } catch (error: any) {
      toast({
        title: 'Failed to save configuration',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  const folderTypes = [
    { key: 'facturen', label: 'Facturen (Invoices)', description: 'Main invoices folder' },
    { key: 'invoices', label: 'Invoices', description: 'Alternative invoices folder' },
    { key: 'reports', label: 'Reports', description: 'Generated reports folder' }
  ];

  if (loading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner size="xl" />
        <Text mt={4}>Loading storage configuration...</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      <Box>
        <Heading size="lg" mb={2}>Storage Configuration</Heading>
        <Text color="gray.600">
          Configure Google Drive folder mappings for {tenant}
        </Text>
      </Box>

      {/* Folder Configuration */}
      <Card>
        <CardHeader>
          <Heading size="md">Folder Mappings</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            {folderTypes.map(({ key, label, description }) => {
              const folderId = config[`${key}_folder_id` as keyof StorageConfig];
              const testResult = testResults[key];
              
              return (
                <Box key={key} p={4} borderWidth={1} borderRadius="md">
                  <FormControl>
                    <FormLabel fontWeight="bold">{label}</FormLabel>
                    <Text fontSize="sm" color="gray.600" mb={2}>{description}</Text>
                    
                    <HStack spacing={2}>
                      <Select
                        placeholder="Select folder"
                        value={folderId || ''}
                        onChange={(e) => handleSelectFolder(key, e.target.value)}
                        flex={1}
                      >
                        {folders.map(folder => (
                          <option key={folder.id} value={folder.id}>
                            {folder.name}
                          </option>
                        ))}
                      </Select>
                      
                      <Button
                        onClick={() => handleTestFolder(key)}
                        isLoading={testing === key}
                        isDisabled={!folderId}
                        colorScheme="blue"
                        variant="outline"
                      >
                        Test
                      </Button>
                    </HStack>

                    {testResult && (
                      <Alert status={testResult.accessible ? 'success' : 'error'} mt={2}>
                        <AlertIcon />
                        <Box flex={1}>
                          <Text fontSize="sm">
                            Read: {testResult.read_access ? '✓' : '✗'} | 
                            Write: {testResult.write_access ? '✓' : '✗'}
                            {testResult.file_count !== undefined && ` | Files: ${testResult.file_count}`}
                          </Text>
                        </Box>
                      </Alert>
                    )}
                  </FormControl>
                </Box>
              );
            })}
          </VStack>

          <Divider my={4} />

          <HStack justify="flex-end">
            <Button onClick={loadData} variant="outline">
              Refresh
            </Button>
            <Button
              onClick={handleSaveConfig}
              isLoading={saving}
              colorScheme="blue"
            >
              Save Configuration
            </Button>
          </HStack>
        </CardBody>
      </Card>

      {/* Storage Usage */}
      {Object.keys(usage).length > 0 && (
        <Card>
          <CardHeader>
            <Heading size="md">Storage Usage</Heading>
          </CardHeader>
          <CardBody>
            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
              {Object.entries(usage).map(([folderName, stats]) => (
                <Stat key={folderName} p={4} borderWidth={1} borderRadius="md">
                  <StatLabel textTransform="capitalize">{folderName}</StatLabel>
                  {stats.accessible ? (
                    <>
                      <StatNumber>{stats.total_size_mb} MB</StatNumber>
                      <StatHelpText>{stats.file_count} files</StatHelpText>
                    </>
                  ) : (
                    <>
                      <StatNumber>—</StatNumber>
                      <StatHelpText color="red.500">Not accessible</StatHelpText>
                    </>
                  )}
                </Stat>
              ))}
            </SimpleGrid>
          </CardBody>
        </Card>
      )}

      {/* Available Folders */}
      <Card>
        <CardHeader>
          <Heading size="md">Available Folders ({folders.length})</Heading>
        </CardHeader>
        <CardBody>
          <Box maxH="300px" overflowY="auto">
            <Table size="sm">
              <Thead>
                <Tr>
                  <Th>Folder Name</Th>
                  <Th>Folder ID</Th>
                  <Th>Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {folders.map(folder => {
                  const isUsed = Object.values(config).includes(folder.id);
                  return (
                    <Tr key={folder.id}>
                      <Td>{folder.name}</Td>
                      <Td fontSize="xs" fontFamily="mono">{folder.id}</Td>
                      <Td>
                        {isUsed && <Badge colorScheme="green">In Use</Badge>}
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </Table>
          </Box>
        </CardBody>
      </Card>
    </VStack>
  );
}
