/**
 * Example usage of AuthContext
 * 
 * This file demonstrates how to use the useAuth hook in components.
 */

import React from 'react';
import { useAuth } from './AuthContext';
import { Box, Button, Text, VStack, Badge, Spinner } from '@chakra-ui/react';

/**
 * Example component showing authentication state
 */
export function AuthStatusExample() {
  const { user, loading, isAuthenticated, logout } = useAuth();

  if (loading) {
    return (
      <Box p={4}>
        <Spinner />
        <Text ml={2}>Loading authentication...</Text>
      </Box>
    );
  }

  if (!isAuthenticated) {
    return (
      <Box p={4}>
        <Text>Not authenticated. Please login.</Text>
      </Box>
    );
  }

  return (
    <VStack align="start" spacing={3} p={4}>
      <Text fontSize="xl">Welcome, {user?.email || user?.username}!</Text>
      
      <Box>
        <Text fontWeight="bold">Your Roles:</Text>
        {user?.roles.map((role) => (
          <Badge key={role} colorScheme="blue" mr={2}>
            {role}
          </Badge>
        ))}
      </Box>

      <Button colorScheme="red" onClick={logout}>
        Logout
      </Button>
    </VStack>
  );
}

/**
 * Example component with role-based rendering
 */
export function RoleBasedExample() {
  const { hasRole, hasAnyRole, isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Text>Please login to view this content.</Text>;
  }

  return (
    <VStack align="start" spacing={3} p={4}>
      {/* Show admin panel only to administrators */}
      {hasRole('Administrators') && (
        <Box p={4} bg="red.100" borderRadius="md">
          <Text fontWeight="bold">Admin Panel</Text>
          <Text>Only administrators can see this.</Text>
        </Box>
      )}

      {/* Show financial data to admins and accountants */}
      {hasAnyRole(['Administrators', 'Finance_CRUD', 'Finance_Read']) && (
        <Box p={4} bg="green.100" borderRadius="md">
          <Text fontWeight="bold">Financial Data</Text>
          <Text>Admins and finance users can see this.</Text>
        </Box>
      )}

      {/* Show reports to all authenticated users */}
      <Box p={4} bg="blue.100" borderRadius="md">
        <Text fontWeight="bold">Reports</Text>
        <Text>All authenticated users can see this.</Text>
      </Box>
    </VStack>
  );
}

/**
 * Example component with role validation
 */
export function RoleValidationExample() {
  const { validateRoles, isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Text>Please login to view role validation.</Text>;
  }

  const validation = validateRoles();

  return (
    <VStack align="start" spacing={3} p={4}>
      <Text fontSize="xl">Role Validation</Text>

      <Box>
        <Text>
          <strong>Valid:</strong> {validation.isValid ? '✅' : '❌'}
        </Text>
        <Text>
          <strong>Has Permissions:</strong> {validation.hasPermissions ? '✅' : '❌'}
        </Text>
        <Text>
          <strong>Has Tenants:</strong> {validation.hasTenants ? '✅' : '❌'}
        </Text>
      </Box>

      {validation.missingRoles.length > 0 && (
        <Box p={3} bg="yellow.100" borderRadius="md">
          <Text fontWeight="bold">Missing Roles:</Text>
          {validation.missingRoles.map((role) => (
            <Text key={role}>• {role}</Text>
          ))}
        </Box>
      )}

      <Box>
        <Text fontWeight="bold">Current Roles:</Text>
        {user?.roles.map((role) => (
          <Badge key={role} colorScheme="purple" mr={2}>
            {role}
          </Badge>
        ))}
      </Box>
    </VStack>
  );
}
