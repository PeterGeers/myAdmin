import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Button, Table, Thead, Tbody, Tr, Th, Td,
  Badge, useToast, Spinner, Text, Modal, ModalOverlay, ModalContent,
  ModalHeader, ModalBody, ModalFooter, ModalCloseButton, useDisclosure,
  Divider, Checkbox, Stack, FormControl, FormLabel, Input
} from '@chakra-ui/react';
import { EditIcon, AddIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '../config';

interface User {
  username: string;
  email: string;
  status: string;
  enabled: boolean;
  groups: string[];
  created: string;
}

interface Group {
  name: string;
  description: string;
  precedence: number;
}

export default function SystemAdmin() {
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [modalMode, setModalMode] = useState<'edit' | 'create'>('edit');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const loadData = async () => {
    setLoading(true);
    try {
      // Get JWT token from Amplify session
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      if (!token) {
        throw new Error('No authentication token available');
      }

      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      const [usersRes, groupsRes] = await Promise.all([
        fetch(buildApiUrl('/api/admin/users'), { headers }),
        fetch(buildApiUrl('/api/admin/groups'), { headers })
      ]);

      if (usersRes.ok && groupsRes.ok) {
        const usersData = await usersRes.json();
        const groupsData = await groupsRes.json();
        setUsers(usersData.users || []);
        setGroups(groupsData.groups || []);
      } else {
        throw new Error('Failed to load data');
      }
    } catch (error) {
      toast({
        title: 'Error loading data',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEditModal = (user: User) => {
    setSelectedUser(user);
    setSelectedRoles([...user.groups]);
    setModalMode('edit');
    onOpen();
  };

  const openCreateModal = () => {
    setSelectedUser(null);
    setNewUserEmail('');
    setNewUserPassword('');
    setSelectedRoles([]);
    setModalMode('create');
    onOpen();
  };

  const closeModal = () => {
    setSelectedUser(null);
    setNewUserEmail('');
    setNewUserPassword('');
    setSelectedRoles([]);
    onClose();
  };

  const toggleRole = (roleName: string) => {
    setSelectedRoles(prev => 
      prev.includes(roleName) 
        ? prev.filter(r => r !== roleName)
        : [...prev, roleName]
    );
  };

  const handleSaveUser = async () => {
    if (modalMode === 'edit' && selectedUser) {
      await updateUserRoles();
    } else if (modalMode === 'create') {
      await createUser();
    }
  };

  const createUser = async () => {
    if (!newUserEmail || !newUserPassword) {
      toast({
        title: 'Validation Error',
        description: 'Email and password are required',
        status: 'error',
        duration: 3000,
      });
      return;
    }

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl('/api/admin/users'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: newUserEmail,
          password: newUserPassword,
          groups: selectedRoles
        })
      });

      if (response.ok) {
        toast({
          title: 'Success',
          description: 'User created successfully',
          status: 'success',
          duration: 3000,
        });
        await loadData();
        closeModal();
      } else {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create user');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const updateUserRoles = async () => {
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      // Determine roles to add and remove
      const rolesToAdd = selectedRoles.filter(r => !selectedUser.groups.includes(r));
      const rolesToRemove = selectedUser.groups.filter(r => !selectedRoles.includes(r));

      // Add roles
      for (const role of rolesToAdd) {
        await fetch(buildApiUrl(`/api/admin/users/${selectedUser.username}/groups`), {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ groupName: role })
        });
      }

      // Remove roles
      for (const role of rolesToRemove) {
        await fetch(buildApiUrl(`/api/admin/users/${selectedUser.username}/groups/${role}`), {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`,
          }
        });
      }

      toast({
        title: 'Success',
        description: 'User roles updated',
        status: 'success',
        duration: 3000,
      });
      await loadData();
      closeModal();
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const toggleUserStatus = async (enable: boolean) => {
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const action = enable ? 'enable' : 'disable';
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.username}/${action}`), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (response.ok) {
        toast({
          title: 'Success',
          description: `User ${enable ? 'enabled' : 'disabled'}`,
          status: 'success',
          duration: 3000,
        });
        await loadData();
        closeModal();
      } else {
        throw new Error(`Failed to ${action} user`);
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const deleteUser = async () => {
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.username}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (response.ok) {
        toast({
          title: 'Success',
          description: 'User deleted',
          status: 'success',
          duration: 3000,
        });
        await loadData();
        closeModal();
      } else {
        throw new Error('Failed to delete user');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Box p={8} display="flex" justifyContent="center">
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <Box p={8}>
      <VStack spacing={8} align="stretch">
        {/* Header with Add User Button */}
        <HStack justify="space-between">
          <Heading color="orange.400" size="xl">User & Role Management</Heading>
          <Button 
            leftIcon={<AddIcon />}
            colorScheme="orange" 
            onClick={openCreateModal}
          >
            Add User
          </Button>
        </HStack>

        {/* Users Table */}
        <Box>
          <Heading size="md" color="gray.300" mb={4}>Users ({users.length})</Heading>
          <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th color="gray.400">Email</Th>
                  <Th color="gray.400">Status</Th>
                  <Th color="gray.400">Roles</Th>
                  <Th color="gray.400">Created</Th>
                  <Th color="gray.400">Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {users.map((user) => (
                  <Tr key={user.username} _hover={{ bg: 'gray.700' }}>
                    <Td color="gray.300">{user.email}</Td>
                    <Td>
                      <Badge colorScheme={user.enabled ? 'green' : 'red'}>
                        {user.status}
                      </Badge>
                    </Td>
                    <Td>
                      <HStack spacing={2} flexWrap="wrap">
                        {user.groups.length > 0 ? (
                          user.groups.map((group) => (
                            <Badge key={group} colorScheme="blue">
                              {group}
                            </Badge>
                          ))
                        ) : (
                          <Text color="gray.500" fontSize="sm">No roles</Text>
                        )}
                      </HStack>
                    </Td>
                    <Td color="gray.400" fontSize="xs">
                      {new Date(user.created).toLocaleDateString()}
                    </Td>
                    <Td>
                      <Button 
                        size="sm" 
                        leftIcon={<EditIcon />}
                        colorScheme="orange" 
                        variant="ghost"
                        onClick={() => openEditModal(user)}
                      >
                        Manage
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        </Box>

        {/* Available Roles */}
        <Box>
          <Heading size="md" color="gray.300" mb={4}>Available Roles ({groups.length})</Heading>
          <Box bg="gray.800" borderRadius="md" p={4}>
            <VStack align="stretch" spacing={2}>
              {groups.map((group) => (
                <HStack key={group.name} justify="space-between" p={3} bg="gray.700" borderRadius="md">
                  <VStack align="start" spacing={0}>
                    <Text color="orange.400" fontWeight="bold">{group.name}</Text>
                    <Text color="gray.400" fontSize="sm">{group.description}</Text>
                  </VStack>
                  <Badge colorScheme="purple">Precedence: {group.precedence}</Badge>
                </HStack>
              ))}
            </VStack>
          </Box>
        </Box>
      </VStack>

      {/* User Management Modal */}
      <Modal isOpen={isOpen} onClose={closeModal} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">
            {modalMode === 'edit' ? `Manage User: ${selectedUser?.email}` : 'Create New User'}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={6} align="stretch">
              {/* Create User Form */}
              {modalMode === 'create' && (
                <>
                  <FormControl isRequired>
                    <FormLabel color="gray.300">Email</FormLabel>
                    <Input
                      type="email"
                      placeholder="user@example.com"
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      bg="gray.700"
                      borderColor="gray.600"
                      _hover={{ borderColor: 'gray.500' }}
                      _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                    />
                  </FormControl>
                  <FormControl isRequired>
                    <FormLabel color="gray.300">Temporary Password</FormLabel>
                    <Input
                      type="password"
                      placeholder="Minimum 8 characters"
                      value={newUserPassword}
                      onChange={(e) => setNewUserPassword(e.target.value)}
                      bg="gray.700"
                      borderColor="gray.600"
                      _hover={{ borderColor: 'gray.500' }}
                      _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                    />
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      User will be required to change password on first login
                    </Text>
                  </FormControl>
                  <Divider borderColor="gray.600" />
                </>
              )}

              {/* User Status (Edit Mode Only) */}
              {modalMode === 'edit' && selectedUser && (
                <>
                  <Box>
                    <Text color="gray.300" fontWeight="bold" mb={2}>User Status</Text>
                    <HStack>
                      <Badge colorScheme={selectedUser.enabled ? 'green' : 'red'} fontSize="md" p={2}>
                        {selectedUser.status}
                      </Badge>
                      <Text color="gray.400" fontSize="sm">
                        Created: {new Date(selectedUser.created).toLocaleDateString()}
                      </Text>
                    </HStack>
                  </Box>
                  <Divider borderColor="gray.600" />
                </>
              )}

              {/* Role Management */}
              <Box>
                <Text color="gray.300" fontWeight="bold" mb={3}>
                  {modalMode === 'edit' ? 'Manage Roles' : 'Assign Roles'}
                </Text>
                <Stack spacing={2}>
                  {groups.map((group) => (
                    <Box
                      key={group.name}
                      p={3}
                      bg="gray.700"
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor={selectedRoles.includes(group.name) ? 'orange.400' : 'gray.600'}
                    >
                      <Checkbox
                        isChecked={selectedRoles.includes(group.name)}
                        onChange={() => toggleRole(group.name)}
                        colorScheme="orange"
                      >
                        <VStack align="start" spacing={0} ml={2}>
                          <Text color="white" fontWeight="bold">{group.name}</Text>
                          <Text color="gray.400" fontSize="sm">{group.description}</Text>
                        </VStack>
                      </Checkbox>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Danger Zone (Edit Mode Only) */}
              {modalMode === 'edit' && selectedUser && (
                <>
                  <Divider borderColor="gray.600" />
                  <Box>
                    <Text color="red.400" fontWeight="bold" mb={3}>Danger Zone</Text>
                    <VStack spacing={2} align="stretch">
                      <Button
                        colorScheme={selectedUser.enabled ? 'yellow' : 'green'}
                        variant="outline"
                        onClick={() => toggleUserStatus(!selectedUser.enabled)}
                        isLoading={actionLoading}
                        size="sm"
                      >
                        {selectedUser.enabled ? 'Disable User' : 'Enable User'}
                      </Button>
                      <Button
                        colorScheme="red"
                        variant="outline"
                        onClick={deleteUser}
                        isLoading={actionLoading}
                        size="sm"
                      >
                        Delete User Permanently
                      </Button>
                    </VStack>
                  </Box>
                </>
              )}
            </VStack>
          </ModalBody>

          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={closeModal}>
              Cancel
            </Button>
            <Button
              colorScheme="orange"
              onClick={handleSaveUser}
              isLoading={actionLoading}
            >
              {modalMode === 'edit' ? 'Save Changes' : 'Create User'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}
