/**
 * Tenant Admin Dashboard
 * 
 * Main dashboard for Tenant Administrators to manage their tenant.
 * Provides access to various tenant management features.
 */

import React, { useState } from 'react';
import {
  Box,
  Container,
  Heading,
  Text,
  VStack,
  HStack,
  Button,
  SimpleGrid,
  Badge,
} from '@chakra-ui/react';
import { TemplateManagement } from './TemplateManagement';

/**
 * Tenant Admin sections
 */
type TenantAdminSection = 'dashboard' | 'templates' | 'users' | 'credentials' | 'settings';

/**
 * TenantAdminDashboard Component
 */
export const TenantAdminDashboard: React.FC = () => {
  const [currentSection, setCurrentSection] = useState<TenantAdminSection>('dashboard');

  /**
   * Render current section
   */
  const renderSection = () => {
    switch (currentSection) {
      case 'templates':
        return <TemplateManagement />;
      
      case 'users':
        return (
          <Container maxW="container.xl" py={8}>
            <VStack spacing={4} align="start">
              <Heading size="xl">User Management</Heading>
              <Text color="gray.400">Manage users and roles for your tenant</Text>
              <Box bg="yellow.900" p={4} borderRadius="md" w="100%">
                <Text fontSize="sm">
                  🚧 User Management feature coming soon
                </Text>
              </Box>
            </VStack>
          </Container>
        );
      
      case 'credentials':
        return (
          <Container maxW="container.xl" py={8}>
            <VStack spacing={4} align="start">
              <Heading size="xl">Credentials Management</Heading>
              <Text color="gray.400">Manage API keys and integrations</Text>
              <Box bg="yellow.900" p={4} borderRadius="md" w="100%">
                <Text fontSize="sm">
                  🚧 Credentials Management feature coming soon
                </Text>
              </Box>
            </VStack>
          </Container>
        );
      
      case 'settings':
        return (
          <Container maxW="container.xl" py={8}>
            <VStack spacing={4} align="start">
              <Heading size="xl">Tenant Settings</Heading>
              <Text color="gray.400">Configure your tenant settings</Text>
              <Box bg="yellow.900" p={4} borderRadius="md" w="100%">
                <Text fontSize="sm">
                  🚧 Tenant Settings feature coming soon
                </Text>
              </Box>
            </VStack>
          </Container>
        );
      
      default:
        return (
          <Container maxW="container.xl" py={8}>
            <VStack spacing={8} align="stretch">
              <VStack spacing={2} align="start">
                <Heading size="xl">Tenant Administration</Heading>
                <Text color="gray.400">
                  Manage your tenant configuration, users, and templates
                </Text>
              </VStack>

              <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={6}>
                {/* Template Management */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  _hover={{ borderColor: 'brand.orange', cursor: 'pointer' }}
                  onClick={() => setCurrentSection('templates')}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">📝</Text>
                      <Badge colorScheme="green">Available</Badge>
                    </HStack>
                    <Heading size="md">Template Management</Heading>
                    <Text fontSize="sm" color="gray.400">
                      Upload and customize report templates for your organization
                    </Text>
                    <Button size="sm" colorScheme="orange" w="100%">
                      Manage Templates →
                    </Button>
                  </VStack>
                </Box>

                {/* User Management */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  opacity={0.6}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">👥</Text>
                      <Badge colorScheme="yellow">Coming Soon</Badge>
                    </HStack>
                    <Heading size="md">User Management</Heading>
                    <Text fontSize="sm" color="gray.400">
                      Manage users and assign roles for your tenant
                    </Text>
                    <Button size="sm" variant="outline" w="100%" isDisabled>
                      Coming Soon
                    </Button>
                  </VStack>
                </Box>

                {/* Credentials Management */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  opacity={0.6}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">🔑</Text>
                      <Badge colorScheme="yellow">Coming Soon</Badge>
                    </HStack>
                    <Heading size="md">Credentials</Heading>
                    <Text fontSize="sm" color="gray.400">
                      Manage API keys and integration credentials
                    </Text>
                    <Button size="sm" variant="outline" w="100%" isDisabled>
                      Coming Soon
                    </Button>
                  </VStack>
                </Box>

                {/* Tenant Settings */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  opacity={0.6}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">⚙️</Text>
                      <Badge colorScheme="yellow">Coming Soon</Badge>
                    </HStack>
                    <Heading size="md">Tenant Settings</Heading>
                    <Text fontSize="sm" color="gray.400">
                      Configure general tenant settings and preferences
                    </Text>
                    <Button size="sm" variant="outline" w="100%" isDisabled>
                      Coming Soon
                    </Button>
                  </VStack>
                </Box>

                {/* Storage Configuration */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  opacity={0.6}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">💾</Text>
                      <Badge colorScheme="yellow">Coming Soon</Badge>
                    </HStack>
                    <Heading size="md">Storage Config</Heading>
                    <Text fontSize="sm" color="gray.400">
                      Configure Google Drive folders and storage options
                    </Text>
                    <Button size="sm" variant="outline" w="100%" isDisabled>
                      Coming Soon
                    </Button>
                  </VStack>
                </Box>

                {/* Audit Logs */}
                <Box
                  bg="brand.gray"
                  p={6}
                  borderRadius="lg"
                  border="1px solid"
                  borderColor="gray.700"
                  opacity={0.6}
                >
                  <VStack align="start" spacing={3}>
                    <HStack>
                      <Text fontSize="3xl">📋</Text>
                      <Badge colorScheme="yellow">Coming Soon</Badge>
                    </HStack>
                    <Heading size="md">Audit Logs</Heading>
                    <Text fontSize="sm" color="gray.400">
                      View audit logs and activity history
                    </Text>
                    <Button size="sm" variant="outline" w="100%" isDisabled>
                      Coming Soon
                    </Button>
                  </VStack>
                </Box>
              </SimpleGrid>
            </VStack>
          </Container>
        );
    }
  };

  return (
    <Box>
      {/* Breadcrumb / Back Button */}
      {currentSection !== 'dashboard' && (
        <Box bg="gray.800" p={4} borderBottom="1px solid" borderColor="gray.700">
          <Container maxW="container.xl">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setCurrentSection('dashboard')}
            >
              ← Back to Tenant Admin
            </Button>
          </Container>
        </Box>
      )}

      {/* Content */}
      {renderSection()}
    </Box>
  );
};

export default TenantAdminDashboard;
