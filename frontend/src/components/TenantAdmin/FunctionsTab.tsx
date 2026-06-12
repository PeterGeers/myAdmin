/**
 * Functions Tab - Toggle optional functions on/off per tenant
 *
 * Displays all optional functions from the FUNCTION_REGISTRY with their
 * current activation state. Functions whose parent module is inactive
 * are greyed out and cannot be toggled.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Text, Spinner, useToast, Badge,
  Switch, Tooltip, Alert, AlertIcon,
} from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../../services/apiService';

interface FunctionState {
  function_name: string;
  parent_module: string;
  label: string;
  is_active: boolean;
  module_active: boolean;
  effective: boolean;
}

interface FunctionsTabProps {
  tenant: string;
}

export default function FunctionsTab({ tenant }: FunctionsTabProps) {
  const toast = useToast();
  const [functions, setFunctions] = useState<FunctionState[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  const loadFunctions = useCallback(async () => {
    try {
      setLoading(true);
      const response = await authenticatedGet('/api/tenant/functions');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const result = await response.json();
      setFunctions(result.data || []);
    } catch (err) {
      console.error('Failed to fetch tenant functions:', err);
      toast({
        title: 'Error loading functions',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
      setFunctions([]);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadFunctions();
  }, [loadFunctions, tenant]);

  const handleToggle = async (functionName: string, currentActive: boolean) => {
    setToggling(functionName);
    try {
      const response = await authenticatedPost('/api/tenant/functions', {
        function_name: functionName,
        is_active: !currentActive,
      });

      const result = await response.json();

      if (response.ok && result.success) {
        toast({
          title: 'Function updated',
          description: `${functionName} is now ${!currentActive ? 'enabled' : 'disabled'}`,
          status: 'success',
          duration: 3000,
        });
        await loadFunctions();
      } else {
        toast({
          title: 'Toggle failed',
          description: result.error || 'Unknown error',
          status: 'error',
          duration: 5000,
        });
      }
    } catch (err) {
      console.error('Failed to toggle function:', err);
      toast({
        title: 'Toggle failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setToggling(null);
    }
  };

  if (loading) {
    return (
      <Box p={4}>
        <Spinner color="orange.400" />
        <Text color="gray.400" ml={2} display="inline">Loading functions...</Text>
      </Box>
    );
  }

  if (functions.length === 0) {
    return (
      <Box p={4}>
        <Alert status="info" bg="blue.900" borderRadius="md">
          <AlertIcon />
          <Text color="gray.100" fontSize="sm">
            No optional functions available for this tenant.
          </Text>
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={3} align="stretch">
        {functions.map((fn) => {
          const isDisabledByModule = !fn.module_active;
          const isToggling = toggling === fn.function_name;

          return (
            <HStack
              key={fn.function_name}
              bg="gray.800"
              p={4}
              borderRadius="md"
              justify="space-between"
              opacity={isDisabledByModule ? 0.5 : 1}
            >
              <HStack spacing={3}>
                <Text color={isDisabledByModule ? 'gray.500' : 'white'} fontWeight="medium">
                  {fn.label}
                </Text>
                <Badge
                  colorScheme={fn.module_active ? 'blue' : 'gray'}
                  fontSize="xs"
                >
                  {fn.parent_module}
                </Badge>
              </HStack>

              <Tooltip
                label={
                  isDisabledByModule
                    ? `Parent module ${fn.parent_module} must be active`
                    : fn.is_active
                      ? 'Click to disable'
                      : 'Click to enable'
                }
                hasArrow
              >
                <Box>
                  <Switch
                    colorScheme="orange"
                    isChecked={fn.is_active}
                    isDisabled={isDisabledByModule || isToggling}
                    onChange={() => handleToggle(fn.function_name, fn.is_active)}
                    size="md"
                  />
                </Box>
              </Tooltip>
            </HStack>
          );
        })}
      </VStack>
    </Box>
  );
}
