/**
 * Tenant Config Management Component
 * 
 * Manage key-value configuration entries in tenant_config table.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Badge,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Input, Checkbox, Heading, Card, CardHeader, CardBody
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

interface ConfigEntry {
  id: number;
  config_key: string;
  config_value: string;
  is_secret: boolean;
  created_at: string;
  updated_at: string;
  created_by?: string;
}

interface TenantConfigManagementProps {
  tenant: string;
}

export default function TenantConfigManagement({ tenant }: TenantConfigManagementProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configs, setConfigs] = useState<ConfigEntry[]>([]);
  const [editingConfig, setEditingConfig] = useState<ConfigEntry | null>(null);
  const [isNewConfig, setIsNewConfig] = useState(false);
  
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formIsSecret, setFormIsSecret] = useState(false);
  
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  const loadConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${API_BASE_URL}/api/tenant-admin/config`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load configurations');
      }

      const data = await response.json();
      setConfigs(data.configs || []);
    } catch (error: any) {
      toast({
        title: 'Failed to load configurations',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [tenant, toast]);

  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  const handleOpenNew = () => {
    setIsNewConfig(true);
    setEditingConfig(null);
    setFormKey('');
    setFormValue('');
    setFormIsSecret(false);
    onOpen();
  };

  const handleOpenEdit = (config: ConfigEntry) => {
    setIsNewConfig(false);
    setEditingConfig(config);
    setFormKey(config.config_key);
    setFormValue(config.config_value);
    setFormIsSecret(config.is_secret);
    onOpen();
  };

  const handleSave = async () => {
    if (!formKey.trim()) {
      toast({
        title: 'Key required',
        description: 'Please enter a configuration key',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setSaving(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const url = isNewConfig
        ? `${API_BASE_URL}/api/tenant-admin/config`
        : `${API_BASE_URL}/api/tenant-admin/config/${editingConfig?.id}`;

      const response = await fetch(url, {
        method: isNewConfig ? 'POST' : 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant,
        },
        body: JSON.stringify({
          config_key: formKey,
          config_value: formValue,
          is_secret: formIsSecret,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save configuration');
      }

      toast({
        title: isNewConfig ? 'Configuration created' : 'Configuration updated',
        status: 'success',
        duration: 3000,
      });

      onClose();
      loadConfigs();
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

  const handleShow = async () => {
    if (!editingConfig) return;

    try {
      // Check if it's a Google Drive folder ID
      if (editingConfig.config_key.includes('folder_id') && editingConfig.config_value) {
        const folderId = editingConfig.config_value;
        const folderUrl = `https://drive.google.com/drive/folders/${folderId}`;
        
        toast({
          title: 'Google Drive Folder',
          description: (
            <Box>
              <Text>Folder ID: {folderId}</Text>
              <Text 
                as="a" 
                href={folderUrl} 
                target="_blank" 
                color="blue.300"
                textDecoration="underline"
              >
                Open in Google Drive
              </Text>
            </Box>
          ),
          status: 'info',
          duration: 10000,
          isClosable: true,
        });
        
        // Also open in new tab
        window.open(folderUrl, '_blank');
      } else {
        // For non-folder configs, just show the value
        toast({
          title: editingConfig.config_key,
          description: `Value: ${editingConfig.config_value}`,
          status: 'info',
          duration: 5000,
          isClosable: true,
        });
      }
    } catch (error: any) {
      toast({
        title: 'Error',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleDelete = async () => {
    if (!editingConfig) return;

    if (!window.confirm(`Delete configuration "${editingConfig.config_key}"?`)) {
      return;
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${API_BASE_URL}/api/tenant-admin/config/${editingConfig.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to delete configuration');
      }

      toast({
        title: 'Configuration deleted',
        status: 'success',
        duration: 3000,
      });

      onClose();
      loadConfigs();
    } catch (error: any) {
      toast({
        title: 'Failed to delete configuration',
        description: error.message,
        status: 'error',
        duration: 5000,
      });
    }
  };

  if (loading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner size="xl" />
        <Text mt={4}>Loading configurations...</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      <Box>
        <Heading size="lg" mb={2}>Tenant Configuration</Heading>
        <Text color="gray.600">
          Manage configuration key-value pairs for {tenant}
        </Text>
      </Box>

      <Card bg="gray.800">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="white">Configuration Entries ({configs.length})</Heading>
            <Button leftIcon={<AddIcon />} colorScheme="orange" onClick={handleOpenNew}>
              Add Configuration
            </Button>
          </HStack>
        </CardHeader>
        <CardBody>
          <Box overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th color="gray.400">Key</Th>
                  <Th color="gray.400">Value</Th>
                  <Th color="gray.400">Secret</Th>
                  <Th color="gray.400">Created</Th>
                  <Th color="gray.400">Updated</Th>
                </Tr>
              </Thead>
              <Tbody>
                {configs.length === 0 ? (
                  <Tr>
                    <Td colSpan={5} textAlign="center" py={8}>
                      <Text color="gray.400">No configurations found. Click "Add Configuration" to create one.</Text>
                    </Td>
                  </Tr>
                ) : (
                  configs.map(config => (
                    <Tr key={config.id}>
                      <Td 
                        fontFamily="mono" 
                        fontSize="sm" 
                        color="orange.400"
                        cursor="pointer"
                        _hover={{ textDecoration: 'underline' }}
                        onClick={() => handleOpenEdit(config)}
                      >
                        {config.config_key}
                      </Td>
                      <Td maxW="300px" isTruncated color="white">
                        {config.is_secret ? '••••••••' : config.config_value}
                      </Td>
                      <Td>
                        {config.is_secret ? (
                          <Badge colorScheme="red">Yes</Badge>
                        ) : (
                          <Badge colorScheme="gray">No</Badge>
                        )}
                      </Td>
                      <Td fontSize="xs" color="gray.400">{new Date(config.created_at).toLocaleDateString()}</Td>
                      <Td fontSize="xs" color="gray.400">{new Date(config.updated_at).toLocaleDateString()}</Td>
                    </Tr>
                  ))
                )}
              </Tbody>
            </Table>
          </Box>
        </CardBody>
      </Card>

      {/* Edit/Create Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="orange.400">
            {isNewConfig ? 'Add Configuration' : 'Edit Configuration'}
          </ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <VStack spacing={4}>
              <FormControl isRequired>
                <FormLabel color="gray.300">Configuration Key</FormLabel>
                <Input
                  value={formKey}
                  onChange={(e) => setFormKey(e.target.value)}
                  placeholder="e.g., google_drive_invoices_folder_id"
                  isDisabled={!isNewConfig}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel color="gray.300">Configuration Value</FormLabel>
                <Input
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  placeholder="Enter value"
                  type={formIsSecret ? 'password' : 'text'}
                  bg="gray.700"
                  color="white"
                  borderColor="gray.600"
                />
              </FormControl>

              <FormControl>
                <Checkbox
                  isChecked={formIsSecret}
                  onChange={(e) => setFormIsSecret(e.target.checked)}
                  colorScheme="orange"
                  color="white"
                >
                  Mark as secret (hide value in table)
                </Checkbox>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            {!isNewConfig && (
              <HStack spacing={2} mr="auto">
                <Button 
                  colorScheme="red" 
                  variant="ghost" 
                  onClick={handleDelete}
                  color="red.400"
                >
                  Delete
                </Button>
                <Button 
                  colorScheme="blue" 
                  variant="ghost" 
                  onClick={handleShow}
                  color="blue.400"
                >
                  Show
                </Button>
              </HStack>
            )}
            <Button variant="ghost" onClick={onClose} color="white">
              Cancel
            </Button>
            <Button colorScheme="orange" onClick={handleSave} isLoading={saving} ml={3}>
              {isNewConfig ? 'Create' : 'Update'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}
