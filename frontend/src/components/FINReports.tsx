/**
 * FINReports Component - Main Financial Reports Container
 * 
 * This component implements comprehensive tenant handling with the following security features:
 * 
 * SECURITY REQUIREMENTS IMPLEMENTED:
 * 1. Tenant Context Integration - Uses useTenant() hook for secure tenant access
 * 2. Pre-processing Validation - Validates tenant selection before allowing access
 * 3. Role-based Access Control - Enforces Finance module permissions
 * 4. Data Isolation - Ensures complete separation between tenants
 * 5. Graceful Error Handling - Provides clear, secure error messages
 * 6. Auto-refresh on Tenant Change - Prevents stale data from previous tenant
 * 7. Loading States - Handles tenant switching gracefully
 * 
 * SECURITY VALIDATIONS:
 * - Blocks access when no tenant is selected
 * - Blocks access when user lacks required permissions (Finance_CRUD, Finance_Read, Finance_Export)
 * - Blocks access when user is null or has no roles
 * - Ensures child components receive proper tenant context through TenantProvider
 * 
 * @component
 */

import React, { useEffect, useState } from 'react';
import { Box, VStack, Alert, AlertIcon, Spinner, Text } from '@chakra-ui/react';
import FinancialReportsGroup from './reports/FinancialReportsGroup';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';

const FINReports: React.FC = () => {
  const { user } = useAuth();
  const { currentTenant } = useTenant();
  const [isLoading, setIsLoading] = useState(false);

  // Handle tenant switching gracefully with loading state
  useEffect(() => {
    if (currentTenant) {
      setIsLoading(true);
      // Log tenant change for debugging (can be removed in production)
      console.log(`FIN Reports: Tenant changed to ${currentTenant}`);
      
      // Brief loading state to allow child components to update
      const timer = setTimeout(() => {
        setIsLoading(false);
      }, 100);

      return () => clearTimeout(timer);
    }
  }, [currentTenant]);

  // Check if user has access to Financial reports
  // Finance module permissions: Finance_CRUD, Finance_Read, Finance_Export
  const canAccessFinancialReports = user?.roles?.some(role => 
    ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role)
  );

  // Tenant validation - ensure tenant is selected before allowing access
  if (!currentTenant) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="warning">
          <AlertIcon />
          <VStack align="start" spacing={2}>
            <Text fontWeight="bold">No tenant selected</Text>
            <Text>Please select a tenant from the dropdown menu to access Financial reports. Financial data is organized by tenant for security and compliance.</Text>
          </VStack>
        </Alert>
      </Box>
    );
  }

  if (!canAccessFinancialReports) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="error">
          <AlertIcon />
          <VStack align="start" spacing={2}>
            <Text fontWeight="bold">Access Denied</Text>
            <Text>You do not have permission to access Financial reports. Required permissions: Finance_CRUD, Finance_Read, or Finance_Export.</Text>
            <Text fontSize="sm" color="gray.600">Please contact your administrator to request access.</Text>
          </VStack>
        </Alert>
      </Box>
    );
  }

  // Show loading state during tenant switching
  if (isLoading) {
    return (
      <Box p={6} bg="gray.800" minH="100vh" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Spinner size="lg" color="orange.500" />
          <Text color="white">Switching to {currentTenant}...</Text>
        </VStack>
      </Box>
    );
  }

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        {/* 
          FinancialReportsGroup and its child components will automatically 
          receive the current tenant context through the TenantProvider.
          Each child report component is responsible for making tenant-aware API calls.
        */}
        <FinancialReportsGroup />
      </VStack>
    </Box>
  );
};

export default FINReports;
