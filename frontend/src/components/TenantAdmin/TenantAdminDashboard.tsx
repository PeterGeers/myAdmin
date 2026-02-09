import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Tabs, TabList, TabPanels, Tab, TabPanel,
  useToast, Spinner, Text, Alert, AlertIcon
} from '@chakra-ui/react';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useTenant } from '../../context/TenantContext';
import UserManagement from './UserManagement';
import TemplateManagement from './TemplateManagement/TemplateManagement';
import CredentialsManagement from './CredentialsManagement';

interface TenantInfo {
  name: string;
  displayName: string;
}

export function TenantAdminDashboard() {
  const [loading, setLoading] = useState(true);
  const [userTenants, setUserTenants] = useState<TenantInfo[]>([]);
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const toast = useToast();
  const { currentTenant } = useTenant(); // Just read from context, don't manage it here

  useEffect(() => {
    loadUserInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadUserInfo = async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      if (!token) {
        throw new Error('No authentication token available');
      }

      // Decode JWT to get user's tenants and roles
      const payload = JSON.parse(atob(token.split('.')[1]));
      const tenants = payload['custom:tenants'] ? JSON.parse(payload['custom:tenants']) : [];
      const roles = payload['cognito:groups'] || [];

      // Check if user has Tenant_Admin role
      if (!roles.includes('Tenant_Admin')) {
        toast({
          title: 'Access Denied',
          description: 'You do not have Tenant Admin permissions',
          status: 'error',
          duration: 5000,
        });
        return;
      }

      setUserRoles(roles);
      
      // Convert tenant names to TenantInfo objects
      const tenantInfos: TenantInfo[] = tenants.map((t: string) => ({
        name: t,
        displayName: t
      }));
      
      setUserTenants(tenantInfos);
      
    } catch (error) {
      toast({
        title: 'Error loading user information',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">Loading Tenant Administration...</Text>
        </VStack>
      </Box>
    );
  }

  if (!userRoles.includes('Tenant_Admin')) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="error">
          <AlertIcon />
          Access Denied: You do not have Tenant Admin permissions
        </Alert>
      </Box>
    );
  }

  if (userTenants.length === 0) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="warning">
          <AlertIcon />
          No tenants assigned to your account
        </Alert>
      </Box>
    );
  }

  if (!currentTenant) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="info">
          <AlertIcon />
          Please select a tenant from the header to continue
        </Alert>
      </Box>
    );
  }

  return (
    <Box minH="100vh" bg="gray.900" p={6}>
      <VStack spacing={6} align="stretch">
        {/* Current Tenant Indicator */}
        <HStack justify="flex-end">
          <Text color="gray.400" fontSize="sm">
            Managing: <Text as="span" color="orange.400" fontWeight="bold">{currentTenant}</Text>
          </Text>
        </HStack>

        {/* Tabs */}
        <Tabs colorScheme="orange" variant="enclosed">
          <TabList>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              User Management
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              Template Management
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              Credentials
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }} isDisabled>
              Tenant Settings
            </Tab>
          </TabList>

          <TabPanels>
            <TabPanel>
              <UserManagement tenant={currentTenant} />
            </TabPanel>
            <TabPanel>
              <TemplateManagement />
            </TabPanel>
            <TabPanel>
              <CredentialsManagement tenant={currentTenant} />
            </TabPanel>
            <TabPanel>
              <Text color="gray.400">Tenant Settings - Coming Soon</Text>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
}

export default TenantAdminDashboard;
