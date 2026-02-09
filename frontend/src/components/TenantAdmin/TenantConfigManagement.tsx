/**
 * Tenant Config Management Component
 * 
 * Manage key-value configuration entries in tenant_config table.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Badge, IconButton,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Input, Checkbox, Heading, Card, CardHeader, CardBody
} from '@chakra-ui/react';
import { AddIcon, EditIcon, DeleteIcon } from '@chakra-ui/icons';
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

  const handleDelete = async (config: ConfigEntry) => {
    if (!window.confirm(`Delete configuration "${config.config_key}"?`)) {
      return;
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${API_BASE_URL}/api/tenant-admin/config/${config.id}`, {
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

      <Card>
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md">Configuration Entries ({configs.length})</Heading>
            <Button leftIcon={<AddIcon />} colorScheme="blue" onClick={handleOpenNew}>
              Add Configuration
            </Button>
          </HStack>
        </CardHeader>
        <CardBody>
          <Box overflowX="auto">
            <Table size="sm">
              <Thead>
                <Tr>
                  <Th>Key</Th>
                  <Th>Value</Th>
                  <Th>Secret</Th>
                  <Th>Created</Th>
                  <Th>Updated</Th>
                  <Th>Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {configs.length === 0 ? (
                  <Tr>
                    <Td colSpan={6} textAlign="center" py={8}>
                      <Text color="gray.500">No configurations found. Click "Add Configuration" to create one.</Text>
                    </Td>
                  </Tr>
                ) : (
                  configs.map(config => (
                    <Tr key={config.id}>
                      <Td fontFamily="mono" fontSize="sm">{config.config_key}</Td>
                      <Td maxW="300px" isTruncated>
                        {config.is_secret ? '••••••••' : config.config_value}
                      </Td>
                      <Td>
                        {config.is_secret && <Badge colorScheme="red">Secret</Badge>}
                      </Td>
                      <Td fontSize="xs">{new Date(config.created_at).toLocaleDateString()}</Td>
                      <Td fontSize="xs">{new Date(config.updated_at).toLocaleDateString()}</Td>
                      <Td>
                        <HStack spacing={1}>
                          <IconButton
                            aria-label="Edit"
                            icon={<EditIcon />}
                            size="sm"
                            onClick={() => handleOpenEdit(config)}
                          />
                          <IconButton
                            aria-label="Delete"
                            icon={<DeleteIcon />}
                            size="sm"
                            colorScheme="red"
                            variant="ghost"
                            onClick={() => handleDelete(config)}
                          />
                        </HStack>
                      </Td>
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
        <ModalContent>
          <ModalHeader>
            {isNewConfig ? 'Add Configuration' : 'Edit Configuration'}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4}>
              <FormControl isRequired>
                <FormLabel>Configuration Key</FormLabel>
                <Input
                  value={formKey}
                  onChange={(e) => setFormKey(e.target.value)}
                  placeholder="e.g., storage_facturen_folder_id"
                  isDisabled={!isNewConfig}
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel>Configuration Value</FormLabel>
                <Input
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  placeholder="Enter value"
                  type={formIsSecret ? 'password' : 'text'}
                />
              </FormControl>

              <FormControl>
                <Checkbox
                  isChecked={formIsSecret}
                  onChange={(e) => setFormIsSecret(e.target.checked)}
                >
                  Mark as secret (hide value in table)
                </Checkbox>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose}>
              Cancel
            </Button>
            <Button colorScheme="blue" onClick={handleSave} isLoading={saving}>
              {isNewConfig ? 'Create' : 'Update'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}
