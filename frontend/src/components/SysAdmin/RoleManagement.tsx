import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Input, Textarea, NumberInput, NumberInputField,
  NumberInputStepper, NumberIncrementStepper, NumberDecrementStepper,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { getRoles, createRole, deleteRole, Role } from '../../services/sysadminService';

export function RoleManagement() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleDescription, setNewRoleDescription] = useState('');
  const [newRolePrecedence, setNewRolePrecedence] = useState(100);
  
  const toast = useToast();
  const { isOpen: isCreateOpen, onOpen: onCreateOpen, onClose: onCreateClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  useEffect(() => {
    loadRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRoles = async () => {
    setLoading(true);
    try {
      const data = await getRoles();
      
      const categorizedRoles = data.roles.map(role => {
        let category: 'platform' | 'module' | 'other' = 'other';
        
        if (role.name === 'SysAdmin' || role.name === 'Tenant_Admin') {
          category = 'platform';
        } else if (role.name.includes('_')) {
          category = 'module';
        }
        
        return { ...role, category };
      });
      
      setRoles(categorizedRoles);
    } catch (error) {
      toast({
        title: 'Error loading roles',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRole = async () => {
    if (!newRoleName.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Role name is required',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setActionLoading(true);
    try {
      await createRole({
        name: newRoleName.trim(),
        description: newRoleDescription.trim(),
        precedence: newRolePrecedence
      });

      toast({
        title: 'Role created',
        description: `Role "${newRoleName}" created successfully`,
        status: 'success',
        duration: 3000,
      });

      setNewRoleName('');
      setNewRoleDescription('');
      setNewRolePrecedence(100);
      
      onCreateClose();
      loadRoles();
    } catch (error) {
      toast({
        title: 'Error creating role',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteRole = async () => {
    if (!selectedRole) return;

    setActionLoading(true);
    try {
      await deleteRole(selectedRole.name);

      toast({
        title: 'Role deleted',
        description: `Role "${selectedRole.name}" deleted`,
        status: 'success',
        duration: 3000,
      });

      onDeleteClose();
      setSelectedRole(null);
      loadRoles();
    } catch (error) {
      toast({
        title: 'Error deleting role',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const openDeleteDialog = (role: Role) => {
    setSelectedRole(role);
    onDeleteOpen();
  };

  const getCategoryColor = (category?: string) => {
    switch (category) {
      case 'platform': return 'purple';
      case 'module': return 'blue';
      default: return 'gray';
    }
  };

  const getCategoryLabel = (category?: string) => {
    switch (category) {
      case 'platform': return 'Platform';
      case 'module': return 'Module';
      default: return 'Other';
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">Loading roles...</Text>
        </VStack>
      </Box>
    );
  }

  const platformRoles = roles.filter(r => r.category === 'platform');
  const moduleRoles = roles.filter(r => r.category === 'module');
  const otherRoles = roles.filter(r => r.category === 'other');

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        <HStack justify="space-between">
          <Text color="gray.300" fontSize="lg">
            Total Roles: <Text as="span" color="orange.400" fontWeight="bold">{roles.length}</Text>
          </Text>
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={onCreateOpen}>
            Create Role
          </Button>
        </HStack>

        {platformRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              Platform Roles ({platformRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {platformRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <HStack>
                      <Text color="orange.400" fontWeight="bold">{role.name}</Text>
                      <Badge colorScheme={getCategoryColor(role.category)} fontSize="xs">
                        {getCategoryLabel(role.category)}
                      </Badge>
                    </HStack>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">Precedence: {role.precedence}</Badge>
                    <Button
                      size="sm"
                      colorScheme="red"
                      variant="ghost"
                      leftIcon={<DeleteIcon />}
                      onClick={() => openDeleteDialog(role)}
                      isDisabled={role.name === 'SysAdmin' || role.name === 'Tenant_Admin'}
                    >
                      Delete
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}

        {moduleRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              Module Roles ({moduleRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {moduleRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <HStack>
                      <Text color="orange.400" fontWeight="bold">{role.name}</Text>
                      <Badge colorScheme={getCategoryColor(role.category)} fontSize="xs">
                        {getCategoryLabel(role.category)}
                      </Badge>
                    </HStack>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">Precedence: {role.precedence}</Badge>
                    <Button size="sm" colorScheme="red" variant="ghost" leftIcon={<DeleteIcon />} onClick={() => openDeleteDialog(role)}>
                      Delete
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}

        {otherRoles.length > 0 && (
          <Box>
            <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>
              Other Roles ({otherRoles.length})
            </Text>
            <VStack align="stretch" spacing={2}>
              {otherRoles.map((role) => (
                <HStack key={role.name} justify="space-between" p={4} bg="gray.800" borderRadius="md" borderWidth="1px" borderColor="gray.700">
                  <VStack align="start" spacing={1} flex={1}>
                    <Text color="orange.400" fontWeight="bold">{role.name}</Text>
                    <Text color="gray.400" fontSize="sm">{role.description}</Text>
                  </VStack>
                  <HStack spacing={3}>
                    <Badge colorScheme="purple">Precedence: {role.precedence}</Badge>
                    <Button size="sm" colorScheme="red" variant="ghost" leftIcon={<DeleteIcon />} onClick={() => openDeleteDialog(role)}>
                      Delete
                    </Button>
                  </HStack>
                </HStack>
              ))}
            </VStack>
          </Box>
        )}
      </VStack>

      <Modal isOpen={isCreateOpen} onClose={onCreateClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">Create New Role</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FormLabel color="gray.300">Role Name</FormLabel>
                <Input
                  placeholder="e.g., Finance_Manager"
                  value={newRoleName}
                  onChange={(e) => setNewRoleName(e.target.value)}
                  bg="gray.700"
                  borderColor="gray.600"
                />
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Use underscore for module roles
                </Text>
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Description</FormLabel>
                <Textarea
                  placeholder="Describe the role"
                  value={newRoleDescription}
                  onChange={(e) => setNewRoleDescription(e.target.value)}
                  bg="gray.700"
                  borderColor="gray.600"
                  rows={3}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Precedence</FormLabel>
                <NumberInput
                  value={newRolePrecedence}
                  onChange={(_, value) => setNewRolePrecedence(value)}
                  min={1}
                  max={999}
                  bg="gray.700"
                >
                  <NumberInputField borderColor="gray.600" />
                  <NumberInputStepper>
                    <NumberIncrementStepper borderColor="gray.600" />
                    <NumberDecrementStepper borderColor="gray.600" />
                  </NumberInputStepper>
                </NumberInput>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Lower = higher priority
                </Text>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onCreateClose}>Cancel</Button>
            <Button colorScheme="orange" onClick={handleCreateRole} isLoading={actionLoading}>
              Create Role
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              Delete Role
            </AlertDialogHeader>
            <AlertDialogBody>
              Are you sure you want to delete <Text as="span" fontWeight="bold" color="orange.400">"{selectedRole?.name}"</Text>?
              <br /><br />
              <Text color="red.400">Warning: Users will lose permissions.</Text>
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>Cancel</Button>
              <Button colorScheme="red" onClick={handleDeleteRole} ml={3} isLoading={actionLoading}>
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}

export default RoleManagement;
