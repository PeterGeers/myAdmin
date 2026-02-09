import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, VStack, HStack, Heading, Button, Table, Thead, Tbody, Tr, Th, Td,
  Badge, useToast, Spinner, Text, Modal, ModalOverlay, ModalContent,
  ModalHeader, ModalBody, ModalFooter, ModalCloseButton, useDisclosure,
  Divider, Checkbox, Stack, FormControl, FormLabel, Input, Tabs, TabList,
  TabPanels, Tab, TabPanel, Select
} from '@chakra-ui/react';
import { EditIcon, AddIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '../config';

interface User {
  username: string;
  email: string;
  name?: string;  // Display name from Cognito
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
  const [newUserName, setNewUserName] = useState('');
  const [editUserName, setEditUserName] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  
  // Filter and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [searchName, setSearchName] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<'email' | 'name' | 'status' | 'created'>('email');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  
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

  // Filtered and sorted users
  const filteredAndSortedUsers = useMemo(() => {
    let filtered = [...users];

    // Search filter - email
    if (searchTerm) {
      filtered = filtered.filter(user => 
        user.email.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Search filter - name
    if (searchName) {
      filtered = filtered.filter(user => 
        user.name?.toLowerCase().includes(searchName.toLowerCase())
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(user => 
        user.status === statusFilter
      );
    }

    // Role filter
    if (roleFilter !== 'all') {
      filtered = filtered.filter(user => 
        user.groups.includes(roleFilter)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      let comparison = 0;
      
      switch (sortField) {
        case 'email':
          comparison = a.email.localeCompare(b.email);
          break;
        case 'name':
          comparison = (a.name || '').localeCompare(b.name || '');
          break;
        case 'status':
          comparison = a.status.localeCompare(b.status);
          break;
        case 'created':
          comparison = new Date(a.created).getTime() - new Date(b.created).getTime();
          break;
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return filtered;
  }, [users, searchTerm, searchName, statusFilter, roleFilter, sortField, sortDirection]);

  // Get unique statuses from users for dynamic dropdown
  const uniqueStatuses = useMemo(() => {
    const statuses = new Set(users.map(user => user.status));
    return Array.from(statuses).sort();
  }, [users]);

  const handleSort = (field: 'email' | 'name' | 'status' | 'created') => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const openEditModal = (user: User) => {
    setSelectedUser(user);
    setSelectedRoles([...user.groups]);
    setEditUserName(user.name || '');
    setModalMode('edit');
    onOpen();
  };

  const openCreateModal = () => {
    setSelectedUser(null);
    setNewUserEmail('');
    setNewUserName('');
    setEditUserName('');
    setNewUserPassword('');
    setSelectedRoles([]);
    setModalMode('create');
    onOpen();
  };

  const closeModal = () => {
    setSelectedUser(null);
    setNewUserEmail('');
    setNewUserName('');
    setEditUserName('');
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
          name: newUserName || undefined,
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

      // Update display name if changed
      if (editUserName !== (selectedUser.name || '')) {
        await fetch(buildApiUrl(`/api/admin/users/${selectedUser.username}/attributes`), {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            name: editUserName || undefined 
          })
        });
      }

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
        description: 'User updated successfully',
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
      <VStack spacing={6} align="stretch">
        {/* Header */}
        <Heading color="orange.400" size="xl">User & Role Management</Heading>

        {/* Tabs */}
        <Tabs colorScheme="orange" variant="enclosed">
          <TabList>
            <Tab _selected={{ color: 'orange.400', borderColor: 'orange.400', borderBottomColor: 'gray.800' }}>
              Users ({users.length})
            </Tab>
            <Tab _selected={{ color: 'orange.400', borderColor: 'orange.400', borderBottomColor: 'gray.800' }}>
              Roles ({groups.length})
            </Tab>
          </TabList>

          <TabPanels>
            {/* Users Tab */}
            <TabPanel px={0}>
              <VStack spacing={4} align="stretch">
                {/* Add User Button */}
                <HStack justify="flex-end">
                  <Button 
                    leftIcon={<AddIcon />}
                    colorScheme="orange" 
                    onClick={openCreateModal}
                  >
                    Add User
                  </Button>
                </HStack>

                {/* Users Table */}
                <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
                  {/* Search Row */}
                  <HStack spacing={2} mb={4} wrap="wrap">
                    <Input
                      placeholder="Search Email"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      bg="gray.600"
                      color="white"
                      size="sm"
                      w="200px"
                    />
                    <Input
                      placeholder="Search Name"
                      value={searchName}
                      onChange={(e) => setSearchName(e.target.value)}
                      bg="gray.600"
                      color="white"
                      size="sm"
                      w="200px"
                    />
                    <Select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      bg="gray.600"
                      color="white"
                      size="sm"
                      w="150px"
                    >
                      <option value="all">All Status</option>
                      {uniqueStatuses.map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </Select>
                    <Select
                      value={roleFilter}
                      onChange={(e) => setRoleFilter(e.target.value)}
                      bg="gray.600"
                      color="white"
                      size="sm"
                      w="200px"
                    >
                      <option value="all">All Roles</option>
                      {[...groups].sort((a, b) => a.name.localeCompare(b.name)).map((group) => (
                        <option key={group.name} value={group.name}>
                          {group.name}
                        </option>
                      ))}
                    </Select>
                    <Text color="gray.400" fontSize="sm" whiteSpace="nowrap">
                      {filteredAndSortedUsers.length} of {users.length} users
                    </Text>
                  </HStack>

                  <Table variant="simple" size="sm">
                    <Thead>
                      <Tr>
                        <Th color="white" width="40px"></Th>
                        <Th 
                          color="white" 
                          cursor="pointer" 
                          onClick={() => handleSort('email')}
                        >
                          Email {sortField === 'email' && (sortDirection === 'asc' ? '↑' : '↓')}
                        </Th>
                        <Th 
                          color="white" 
                          cursor="pointer" 
                          onClick={() => handleSort('name')}
                        >
                          Name {sortField === 'name' && (sortDirection === 'asc' ? '↑' : '↓')}
                        </Th>
                        <Th 
                          color="white"
                          cursor="pointer"
                          onClick={() => handleSort('status')}
                        >
                          Status {sortField === 'status' && (sortDirection === 'asc' ? '↑' : '↓')}
                        </Th>
                        <Th color="white">Roles</Th>
                        <Th 
                          color="white"
                          cursor="pointer"
                          onClick={() => handleSort('created')}
                        >
                          Created {sortField === 'created' && (sortDirection === 'asc' ? '↑' : '↓')}
                        </Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {filteredAndSortedUsers.map((user) => (
                        <Tr 
                          key={user.username} 
                          _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                          onClick={() => openEditModal(user)}
                        >
                          <Td>
                            <EditIcon color="orange.400" />
                          </Td>
                          <Td color="gray.300">{user.email}</Td>
                          <Td color="gray.300">{user.name || '-'}</Td>
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
                        </Tr>
                      ))}
                    </Tbody>
                  </Table>
                </Box>
              </VStack>
            </TabPanel>

            {/* Roles Tab */}
            <TabPanel px={0}>
              <VStack spacing={4} align="stretch">
                {/* Add Role Button */}
                <HStack justify="flex-end">
                  <Button 
                    leftIcon={<AddIcon />}
                    colorScheme="orange" 
                    size="sm"
                    onClick={() => {
                      toast({
                        title: 'Coming Soon',
                        description: 'Role creation feature will be available soon',
                        status: 'info',
                        duration: 3000,
                      });
                    }}
                  >
                    Add Role
                  </Button>
                </HStack>

                {/* Roles List */}
                <Box bg="gray.800" borderRadius="md" p={4}>
                  <VStack align="stretch" spacing={2}>
                    {[...groups].sort((a, b) => a.name.localeCompare(b.name)).map((group) => {
                      const userCount = users.filter(user => user.groups.includes(group.name)).length;
                      return (
                        <HStack key={group.name} justify="space-between" p={3} bg="gray.700" borderRadius="md">
                          <VStack align="start" spacing={0} flex={1}>
                            <Text color="orange.400" fontWeight="bold">{group.name}</Text>
                            <Text color="gray.400" fontSize="sm">{group.description}</Text>
                          </VStack>
                          <HStack spacing={3}>
                            <Badge colorScheme="blue" fontSize="sm">
                              {userCount} {userCount === 1 ? 'user' : 'users'}
                            </Badge>
                            <Badge colorScheme="purple">Precedence: {group.precedence}</Badge>
                          </HStack>
                        </HStack>
                      );
                    })}
                  </VStack>
                </Box>
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
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
                  <FormControl>
                    <FormLabel color="gray.300">Display Name</FormLabel>
                    <Input
                      type="text"
                      placeholder="John Doe (optional)"
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                      _hover={{ borderColor: 'gray.500' }}
                      _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                    />
                    <Text fontSize="xs" color="gray.500" mt={1}>
                      This name will be displayed in the application header
                    </Text>
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
                    <Text color="gray.300" fontWeight="bold" mb={3}>User Information</Text>
                    <VStack align="stretch" spacing={3}>
                      <FormControl>
                        <FormLabel color="gray.400" fontSize="sm">Email (cannot be changed)</FormLabel>
                        <Input
                          value={selectedUser.email}
                          isReadOnly
                          bg="gray.900"
                          borderColor="gray.600"
                          color="gray.400"
                          cursor="not-allowed"
                        />
                      </FormControl>
                      
                      <FormControl>
                        <FormLabel color="gray.300">Display Name</FormLabel>
                        <Input
                          type="text"
                          placeholder="John Doe"
                          value={editUserName}
                          onChange={(e) => setEditUserName(e.target.value)}
                          bg="gray.700"
                          color="white"
                          borderColor="gray.600"
                          _hover={{ borderColor: 'gray.500' }}
                          _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                        />
                        <Text fontSize="xs" color="gray.500" mt={1}>
                          This name will be displayed in the application header
                        </Text>
                      </FormControl>

                      <HStack>
                        <Text color="gray.400" fontSize="sm" minW="80px">Status:</Text>
                        <Badge colorScheme={selectedUser.enabled ? 'green' : 'red'} fontSize="md">
                          {selectedUser.status}
                        </Badge>
                      </HStack>
                      <HStack>
                        <Text color="gray.400" fontSize="sm" minW="80px">Created:</Text>
                        <Text color="gray.400" fontSize="sm">
                          {new Date(selectedUser.created).toLocaleDateString()}
                        </Text>
                      </HStack>
                    </VStack>
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
                  {[...groups].sort((a, b) => a.name.localeCompare(b.name)).map((group) => (
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
