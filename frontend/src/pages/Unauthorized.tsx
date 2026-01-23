/**
 * Unauthorized Page Component
 * 
 * Displayed when a user tries to access a resource they don't have permission for.
 */

import React from 'react';
import {
  Box,
  VStack,
  Heading,
  Text,
  Button,
  Container,
  Icon,
  HStack,
  Badge,
  List,
  ListItem,
  ListIcon
} from '@chakra-ui/react';
import { WarningIcon, LockIcon, CheckCircleIcon } from '@chakra-ui/icons';
import { useAuth } from '../context/AuthContext';

interface UnauthorizedProps {
  requiredRoles?: string[];
}

/**
 * Unauthorized Page Component
 * 
 * Shows when user lacks required permissions.
 * Displays current roles and required roles for transparency.
 */
export default function Unauthorized({ requiredRoles = [] }: UnauthorizedProps) {
  const { user, logout } = useAuth();

  const handleGoBack = () => {
    window.history.back();
  };

  return (
    <Box
      minH="100vh"
      bg="gray.900"
      display="flex"
      alignItems="center"
      justifyContent="center"
      px={4}
    >
      <Container maxW="lg">
        <VStack spacing={8} bg="gray.800" p={8} borderRadius="lg" boxShadow="2xl">
          {/* Icon */}
          <Icon as={LockIcon} w={16} h={16} color="red.400" />

          {/* Title */}
          <VStack spacing={2}>
            <Heading color="red.400" size="xl">
              Access Denied
            </Heading>
            <Text color="gray.300" fontSize="lg" textAlign="center">
              You don't have permission to access this resource
            </Text>
          </VStack>

          {/* User Info */}
          {user && (
            <VStack spacing={4} w="full" bg="gray.700" p={4} borderRadius="md">
              <HStack w="full" justify="space-between">
                <Text color="gray.400" fontSize="sm">
                  Logged in as:
                </Text>
                <Text color="orange.400" fontSize="sm" fontWeight="bold">
                  {user.email}
                </Text>
              </HStack>

              {/* Current Roles */}
              {user.roles && user.roles.length > 0 && (
                <VStack w="full" align="start" spacing={2}>
                  <Text color="gray.400" fontSize="sm">
                    Your current roles:
                  </Text>
                  <HStack wrap="wrap" spacing={2}>
                    {user.roles.map((role) => (
                      <Badge key={role} colorScheme="blue" fontSize="xs">
                        {role}
                      </Badge>
                    ))}
                  </HStack>
                </VStack>
              )}

              {/* Required Roles */}
              {requiredRoles.length > 0 && (
                <VStack w="full" align="start" spacing={2}>
                  <Text color="gray.400" fontSize="sm">
                    Required roles (you need at least one):
                  </Text>
                  <List spacing={1}>
                    {requiredRoles.map((role) => (
                      <ListItem key={role} color="gray.300" fontSize="sm">
                        <ListIcon as={CheckCircleIcon} color="green.400" />
                        {role}
                      </ListItem>
                    ))}
                  </List>
                </VStack>
              )}
            </VStack>
          )}

          {/* Warning Message */}
          <Box
            w="full"
            bg="orange.900"
            borderColor="orange.500"
            borderWidth="1px"
            borderRadius="md"
            p={4}
          >
            <HStack spacing={3}>
              <Icon as={WarningIcon} color="orange.400" />
              <VStack align="start" spacing={1}>
                <Text color="orange.200" fontSize="sm" fontWeight="bold">
                  Need Access?
                </Text>
                <Text color="gray.300" fontSize="xs">
                  Contact your administrator to request the necessary permissions.
                </Text>
              </VStack>
            </HStack>
          </Box>

          {/* Actions */}
          <HStack spacing={4} w="full">
            <Button
              size="lg"
              w="full"
              colorScheme="orange"
              onClick={handleGoBack}
            >
              Go Back
            </Button>
            <Button
              size="lg"
              w="full"
              variant="outline"
              colorScheme="gray"
              onClick={logout}
            >
              Logout
            </Button>
          </HStack>
        </VStack>
      </Container>
    </Box>
  );
}
