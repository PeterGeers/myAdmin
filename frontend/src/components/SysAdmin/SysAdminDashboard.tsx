import React, { useState, useEffect } from 'react';
import {
  Box, VStack, Tabs, TabList, TabPanels, Tab, TabPanel,
  useToast, Spinner, Text, Alert, AlertIcon
} from '@chakra-ui/react';
import { fetchAuthSession } from 'aws-amplify/auth';
import RoleManagement from './RoleManagement';
import TenantManagement from './TenantManagement';
import HealthCheck from './HealthCheck';

export function SysAdminDashboard() {
  const [loading, setLoading] = useState(true);
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const toast = useToast();

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

      // Decode JWT to get user's roles
      const payload = JSON.parse(atob(token.split('.')[1]));
      const roles = payload['cognito:groups'] || [];

      // Check if user has SysAdmin role
      if (!roles.includes('SysAdmin')) {
        toast({
          title: 'Access Denied',
          description: 'You do not have System Administrator permissions',
          status: 'error',
          duration: 5000,
        });
        return;
      }

      setUserRoles(roles);
      
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
          <Text color="gray.400">Loading System Administration...</Text>
        </VStack>
      </Box>
    );
  }

  if (!userRoles.includes('SysAdmin')) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="error">
          <AlertIcon />
          Access Denied: You do not have System Administrator permissions
        </Alert>
      </Box>
    );
  }

  return (
    <Box minH="100vh" bg="gray.900" p={6}>
      <VStack spacing={6} align="stretch">
        {/* Tabs for Tenant Management, Role Management, and Health Check */}
        <Tabs colorScheme="orange" variant="enclosed">
          <TabList>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              Tenant Management
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              Role Management
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              Health Check
            </Tab>
          </TabList>

          <TabPanels>
            <TabPanel>
              <TenantManagement />
            </TabPanel>
            <TabPanel>
              <RoleManagement />
            </TabPanel>
            <TabPanel>
              <HealthCheck />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
}

export default SysAdminDashboard;
