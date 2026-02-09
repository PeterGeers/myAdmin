import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, Switch, useToast, Spinner,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, FormControl, FormLabel,
  Alert, AlertIcon, AlertDescription, Tooltip, Icon
} from '@chakra-ui/react';
import { InfoIcon } from '@chakra-ui/icons';
import { getTenantModules, updateTenantModules } from '../../services/sysadminService';

interface ModuleManagementProps {
  administration: string;
  isOpen: boolean;
  onClose: () => void;
}

interface ModuleState {
  name: string;
  is_active: boolean;
  description: string;
  readonly: boolean;
}

const MODULE_DESCRIPTIONS: Record<string, string> = {
  'TENADMIN': 'Tenant Administration - Manage users and settings within tenant',
  'FIN': 'Financial Management - Invoice processing, banking, and reports',
  'STR': 'Short-Term Rental - Booking management, pricing, and analytics',
  'ADMIN': 'Platform Administration - System-wide management (reserved)'
};

export function ModuleManagement({ administration, isOpen, onClose }: ModuleManagementProps) {
  const [modules, setModules] = useState<ModuleState[]>([]);
  const [originalModules, setOriginalModules] = useState<ModuleState[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  
  const toast = useToast();

  useEffect(() => {
    if (isOpen) {
      loadModules();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, administration]);

  useEffect(() => {
    // Check if there are any changes
    const changed = modules.some((mod, idx) => 
      mod.is_active !== originalModules[idx]?.is_active
    );
    setHasChanges(changed);
  }, [modules, originalModules]);

  const loadModules = async () => {
    setLoading(true);
    try {
      const data = await getTenantModules(administration);
      
      // Convert to ModuleState format
      const moduleStates: ModuleState[] = ['TENADMIN', 'FIN', 'STR'].map(moduleName => {
        const existing = data.modules.find(m => m.module_name === moduleName);
        return {
          name: moduleName,
          is_active: existing?.is_active ?? false,
          description: MODULE_DESCRIPTIONS[moduleName] || '',
          readonly: moduleName === 'TENADMIN' // TENADMIN is always enabled
        };
      });
      
      setModules(moduleStates);
      setOriginalModules(JSON.parse(JSON.stringify(moduleStates)));
    } catch (error) {
      toast({
        title: 'Error loading modules',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = (moduleName: string) => {
    setModules(prev => prev.map(mod =>
      mod.name === moduleName ? { ...mod, is_active: !mod.is_active } : mod
    ));
  };

  const handleReset = () => {
    setModules(JSON.parse(JSON.stringify(originalModules)));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const modulesToUpdate = modules.map(mod => ({
        name: mod.name,
        is_active: mod.is_active
      }));

      await updateTenantModules(administration, modulesToUpdate);

      toast({
        title: 'Modules updated',
        description: `Modules for "${administration}" updated successfully`,
        status: 'success',
        duration: 3000,
      });

      setOriginalModules(JSON.parse(JSON.stringify(modules)));
      setHasChanges(false);
      onClose();
    } catch (error) {
      toast({
        title: 'Error updating modules',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="orange.400">
          Module Management: {administration}
        </ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          {loading ? (
            <Box display="flex" justifyContent="center" p={8}>
              <VStack spacing={4}>
                <Spinner size="xl" color="orange.400" />
                <Text color="gray.400">Loading modules...</Text>
              </VStack>
            </Box>
          ) : (
            <VStack spacing={6} align="stretch">
              <Alert status="info" bg="blue.900" borderRadius="md">
                <AlertIcon />
                <AlertDescription color="gray.200" fontSize="sm">
                  <HStack spacing={1}>
                    <Icon as={InfoIcon} />
                    <Text>
                      Disabling a module does not remove users from module groups. 
                      Users will retain their module roles but won't have access to module features.
                    </Text>
                  </HStack>
                </AlertDescription>
              </Alert>

              <VStack spacing={4} align="stretch">
                {modules.map((module) => (
                  <Box
                    key={module.name}
                    p={4}
                    bg="gray.700"
                    borderRadius="md"
                    borderWidth="1px"
                    borderColor="gray.600"
                  >
                    <HStack justify="space-between">
                      <VStack align="start" spacing={1} flex={1}>
                        <HStack>
                          <Text color="orange.400" fontWeight="bold" fontSize="lg">
                            {module.name}
                          </Text>
                          {module.readonly && (
                            <Tooltip label="This module is always enabled">
                              <Text fontSize="xs" color="gray.500">(Required)</Text>
                            </Tooltip>
                          )}
                        </HStack>
                        <Text color="gray.400" fontSize="sm">
                          {module.description}
                        </Text>
                      </VStack>
                      <FormControl display="flex" alignItems="center" width="auto">
                        <FormLabel htmlFor={`module-${module.name}`} mb="0" mr={2} color="gray.300">
                          {module.is_active ? 'Enabled' : 'Disabled'}
                        </FormLabel>
                        <Switch
                          id={`module-${module.name}`}
                          colorScheme="orange"
                          size="lg"
                          isChecked={module.is_active}
                          onChange={() => handleToggle(module.name)}
                          isDisabled={module.readonly}
                        />
                      </FormControl>
                    </HStack>
                  </Box>
                ))}
              </VStack>
            </VStack>
          )}
        </ModalBody>
        <ModalFooter>
          <HStack spacing={3} width="100%" justify="space-between">
            <Button
              variant="ghost"
              onClick={handleReset}
              isDisabled={!hasChanges || saving}
            >
              Reset
            </Button>
            <HStack>
              <Button variant="ghost" onClick={onClose} isDisabled={saving}>
                Cancel
              </Button>
              <Button
                colorScheme="orange"
                onClick={handleSave}
                isLoading={saving}
                isDisabled={!hasChanges}
              >
                Save Changes
              </Button>
            </HStack>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

export default ModuleManagement;
