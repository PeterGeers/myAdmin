/**
 * Tenant Selector Component
 * 
 * Displays a dropdown for users with multiple tenant assignments.
 * Allows switching between tenants without re-authentication.
 */

import React from 'react';
import { Select, HStack, Text } from '@chakra-ui/react';
import { useTenant } from '../context/TenantContext';

/**
 * Props for TenantSelector
 */
interface TenantSelectorProps {
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  hide?: boolean; // Allow parent to force hide (e.g., on SysAdmin pages)
}

/**
 * Tenant Selector Component
 * 
 * Only renders if user has multiple tenants.
 * Can be hidden via prop for platform-level pages (e.g., System Administration).
 * Persists selection to localStorage for convenience.
 */
export default function TenantSelector({ size = 'sm', showLabel = true, hide = false }: TenantSelectorProps) {
  const { currentTenant, availableTenants, setCurrentTenant, hasMultipleTenants } = useTenant();

  // Don't render if explicitly hidden (e.g., on SysAdmin pages)
  if (hide) {
    return null;
  }

  // Don't render if user has no tenants at all or only has single tenant
  if (!availableTenants || availableTenants.length === 0 || !hasMultipleTenants) {
    return null;
  }

  return (
    <HStack spacing={2}>
      {showLabel && (
        <Text color="gray.400" fontSize={size}>
          Tenant:
        </Text>
      )}
      <Select
        value={currentTenant || ''}
        onChange={(e) => setCurrentTenant(e.target.value)}
        size={size}
        variant="filled"
        bg="gray.700"
        color="orange.400"
        borderColor="orange.500"
        _hover={{ bg: 'gray.600' }}
        _focus={{ bg: 'gray.600', borderColor: 'orange.400' }}
        width="auto"
        minW="150px"
      >
        {availableTenants.map((tenant) => (
          <option key={tenant} value={tenant}>
            {tenant}
          </option>
        ))}
      </Select>
    </HStack>
  );
}
