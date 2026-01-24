/**
 * User Menu Component
 * 
 * Displays user information with a popover showing detailed credentials.
 * Shows user name/email with roles and tenant information in a dropdown.
 */

import React from 'react';
import {
  Box,
  Button,
  HStack,
  VStack,
  Text,
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverHeader,
  PopoverBody,
  PopoverArrow,
  PopoverCloseButton,
  Badge,
  Divider
} from '@chakra-ui/react';
import { ChevronDownIcon } from '@chakra-ui/icons';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';

/**
 * Props for UserMenu
 */
interface UserMenuProps {
  onLogout: () => void;
  mode?: string;
}

/**
 * User Menu Component
 * 
 * Displays a button with user name/email that opens a popover with detailed info.
 */
export default function UserMenu({ onLogout, mode }: UserMenuProps) {
  const { user } = useAuth();
  const { currentTenant, availableTenants } = useTenant();

  if (!user) {
    return null;
  }

  // Get display name (prefer name, then email, then username)
  const displayName = user.name || user.email || user.username;

  return (
    <Popover placement="bottom-end">
      <PopoverTrigger>
        <Button
          size="sm"
          variant="ghost"
          colorScheme="orange"
          rightIcon={<ChevronDownIcon />}
          _hover={{ bg: 'gray.700' }}
        >
          <Text color="gray.300">{displayName}</Text>
        </Button>
      </PopoverTrigger>
      <PopoverContent bg="gray.800" borderColor="orange.500" color="white" width="320px">
        <PopoverArrow bg="gray.800" />
        <PopoverCloseButton />
        <PopoverHeader borderColor="gray.700" fontWeight="bold" color="orange.400">
          User Information
        </PopoverHeader>
        <PopoverBody>
          <VStack align="stretch" spacing={3}>
            {/* Environment Mode */}
            {mode && (
              <Box>
                <Text fontSize="xs" color="gray.500" mb={1}>Environment</Text>
                <Badge colorScheme={mode === 'Test' ? 'red' : 'green'} fontSize="sm">
                  {mode} Mode
                </Badge>
              </Box>
            )}

            {mode && <Divider borderColor="gray.700" />}

            {/* Name */}
            {user.name && (
              <Box>
                <Text fontSize="xs" color="gray.500" mb={1}>Name</Text>
                <Text fontSize="sm" color="gray.300">{user.name}</Text>
              </Box>
            )}

            {/* Email */}
            <Box>
              <Text fontSize="xs" color="gray.500" mb={1}>Email</Text>
              <Text fontSize="sm" color="gray.300">{user.email || 'N/A'}</Text>
            </Box>

            {/* Username (only show if different from email) */}
            {user.username !== user.email && (
              <Box>
                <Text fontSize="xs" color="gray.500" mb={1}>User ID</Text>
                <Text fontSize="xs" color="gray.400" fontFamily="mono">{user.username}</Text>
              </Box>
            )}

            <Divider borderColor="gray.700" />

            {/* Roles */}
            <Box>
              <Text fontSize="xs" color="gray.500" mb={2}>Roles</Text>
              <HStack spacing={1} flexWrap="wrap">
                {user.roles && user.roles.length > 0 ? (
                  user.roles.map((role) => (
                    <Badge
                      key={role}
                      colorScheme="blue"
                      fontSize="xs"
                      mb={1}
                    >
                      {role}
                    </Badge>
                  ))
                ) : (
                  <Text fontSize="sm" color="gray.500">No roles assigned</Text>
                )}
              </HStack>
            </Box>

            <Divider borderColor="gray.700" />

            {/* Tenants */}
            <Box>
              <Text fontSize="xs" color="gray.500" mb={2}>Tenants</Text>
              {availableTenants && availableTenants.length > 0 ? (
                <VStack align="stretch" spacing={1}>
                  {availableTenants.map((tenant) => (
                    <HStack key={tenant} spacing={2}>
                      <Badge
                        colorScheme={tenant === currentTenant ? 'orange' : 'gray'}
                        fontSize="xs"
                      >
                        {tenant}
                      </Badge>
                      {tenant === currentTenant && (
                        <Text fontSize="xs" color="orange.400">(current)</Text>
                      )}
                    </HStack>
                  ))}
                </VStack>
              ) : (
                <Text fontSize="sm" color="gray.500">No tenants assigned</Text>
              )}
            </Box>

            <Divider borderColor="gray.700" />

            {/* Logout Button */}
            <Button
              size="sm"
              colorScheme="orange"
              variant="outline"
              onClick={onLogout}
              width="full"
            >
              Logout
            </Button>
          </VStack>
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
}
