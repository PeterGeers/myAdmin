import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, VStack, HStack, Button, Table, Thead, Tbody, Tr, Th, Td,
  Badge, useToast, Spinner, Text, Modal, ModalOverlay, ModalContent,
  ModalHeader, ModalBody, ModalFooter, ModalCloseButton, useDisclosure,
  Checkbox, Stack, FormControl, FormLabel, Input, Select
} from '@chakra-ui/react';
import { EditIcon, AddIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '../../config';

interface User {
  username: string;
  email: string;
  name?: string;
  status: string;
  enabled: boolean;
  groups: string[];
  tenants: string[];
  created: string;
}

interface Role {
  name: string;
  description: string;
  precedence: number | null;
}

interface EmailTemplate {
  template_type: string;
  display_name: string;
}

interface UserManagementProps {
  tenant: string;
}

export default function UserManagement({ tenant }: UserManagementProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [modalMode, setModalMode] = useState<'edit' | 'create' | 'details'>('edit');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [editUserName, setEditUserName] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState<string>('user_invitation');
  const [sendingEmail, setSendingEmail] = useState(false);
  
  // Filter and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [searchName, setSearchName] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<'email' | 'name' | 'status' | 'created'>('email');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  // Available email templates
  const emailTemplates: EmailTemplate[] = [
    { template_type: 'user_invitation', display_name: 'User Invitation' },
    { template_type: 'password_reset', display_name: 'Password Reset' },
    { template_type: 'account_update', display_name: 'Account Update Notification' },
  ];

  const loadData = async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      if (!token) {
        throw new Error('No authentication token available');
      }

      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant': tenant
      };

      const [usersRes, rolesRes] = await Promise.all([
        fetch(buildApiUrl('/api/tenant-admin/users'), { headers }),
        fetch(buildApiUrl('/api/tenant-admin/roles'), { headers })
      ]);

      if (usersRes.ok && rolesRes.ok) {
        const usersData = await usersRes.json();
        const rolesData = await rolesRes.json();
        setUsers(usersData.users || []);
        setRoles(rolesData.roles || []);
      } else {
        const usersError = await usersRes.text();
        const rolesError = await rolesRes.text();
        throw new Error(`Failed to load data: ${usersError || rolesError}`);
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
    if (tenant) {
      loadData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  // Filtered and sorted users
  const filteredAndSortedUsers = useMemo(() => {
    let filtered = users.filter(user => {
      const matchesEmail = user.email.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesName = !searchName || (user.name?.toLowerCase().includes(searchName.toLowerCase()) ?? false);
      const matchesStatus = statusFilter === 'all' || user.status === statusFilter;
      const matchesRole = roleFilter === 'all' || user.groups.includes(roleFilter);
      
      return matchesEmail && matchesName && matchesStatus && matchesRole;
    });

    // Sort
    filtered.sort((a, b) => {
      let aVal: string | number = '';
      let bVal: string | number = '';

      switch (sortField) {
        case 'email':
          aVal = a.email;
          bVal = b.email;
          break;
        case 'name':
          aVal = a.name || '';
          bVal = b.name || '';
          break;
        case 'status':
          aVal = a.status;
          bVal = b.status;
          break;
        case 'created':
          aVal = new Date(a.created).getTime();
          bVal = new Date(b.created).getTime();
          break;
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });

    return filtered;
  }, [users, searchTerm, searchName, statusFilter, roleFilter, sortField, sortDirection]);

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const openCreateModal = () => {
    setModalMode('create');
    setNewUserEmail('');
    setNewUserName('');
    setNewUserPassword('');
    setSelectedRoles([]);
    onOpen();
  };

  const openEditModal = (user: User) => {
    setModalMode('edit');
    setSelectedUser(user);
    setEditUserName(user.name || '');
    setSelectedRoles(user.groups);
    onOpen();
  };

  const openDetailsModal = (user: User) => {
    setModalMode('details');
    setSelectedUser(user);
    setSelectedEmailTemplate('user_invitation');
    onOpen();
  };

  const handleCreateUser = async () => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl('/api/tenant-admin/users'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({
          email: newUserEmail,
          name: newUserName,
          password: newUserPassword,
          groups: selectedRoles
        })
      });

      const data = await response.json();

      if (response.ok) {
        const successMessage = data.existing_user 
          ? `${data.message}. The user already existed and has been added to this tenant.`
          : data.message;
        
        toast({
          title: data.existing_user ? 'User added to tenant' : 'User created',
          description: successMessage,
          status: 'success',
          duration: 5000,
        });
        onClose();
        loadData();
      } else {
        // Handle specific error cases
        if (response.status === 409) {
          // User already in this tenant
          toast({
            title: 'User already exists',
            description: data.message || data.error,
            status: 'warning',
            duration: 5000,
          });
        } else {
          throw new Error(data.error || 'Failed to create user');
        }
      }
    } catch (error) {
      toast({
        title: 'Error creating user',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!selectedUser) return;

    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      // Update display name if changed
      if (editUserName !== (selectedUser.name || '')) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}`), {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Tenant': tenant
          },
          body: JSON.stringify({ name: editUserName })
        });
      }

      // Update roles
      const currentRoles = selectedUser.groups;
      const rolesToAdd = selectedRoles.filter(r => !currentRoles.includes(r));
      const rolesToRemove = currentRoles.filter(r => !selectedRoles.includes(r));

      // Add roles
      for (const role of rolesToAdd) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}/groups`), {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Tenant': tenant
          },
          body: JSON.stringify({ groupName: role })
        });
      }

      // Remove roles
      for (const role of rolesToRemove) {
        await fetch(buildApiUrl(`/api/tenant-admin/users/${selectedUser.username}/groups/${role}`), {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`,
            'X-Tenant': tenant
          }
        });
      }

      toast({
        title: 'User updated',
        status: 'success',
        duration: 3000,
      });
      onClose();
      loadData();
    } catch (error) {
      toast({
        title: 'Error updating user',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleUserStatus = async (user: User, enable: boolean) => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/tenant-admin/users/${user.username}`), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({ enabled: enable })
      });

      if (response.ok) {
        toast({
          title: `User ${enable ? 'enabled' : 'disabled'}`,
          status: 'success',
          duration: 3000,
        });
        loadData();
      } else {
        throw new Error('Failed to update user status');
      }
    } catch (error) {
      toast({
        title: 'Error updating user status',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (!window.confirm(`Are you sure you want to delete user ${user.email}?`)) {
      return;
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/tenant-admin/users/${user.username}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant
        }
      });

      const data = await response.json();

      if (response.ok) {
        toast({
          title: 'User deleted',
          description: data.message,
          status: 'success',
          duration: 3000,
        });
        loadData();
      } else {
        throw new Error(data.error || 'Failed to delete user');
      }
    } catch (error) {
      toast({
        title: 'Error deleting user',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    }
  };

  const handleSendEmail = async () => {
    if (!selectedUser) return;

    setSendingEmail(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl('/api/tenant-admin/send-email'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'X-Tenant': tenant
        },
        body: JSON.stringify({
          email: selectedUser.email,
          template_type: selectedEmailTemplate,
          user_data: {
            name: selectedUser.name,
            username: selectedUser.username,
            status: selectedUser.status
          }
        })
      });

      const data = await response.json();

      if (response.ok) {
        toast({
          title: 'Email sent',
          description: `Email sent successfully to ${selectedUser.email}`,
          status: 'success',
          duration: 3000,
        });
      } else {
        throw new Error(data.error || 'Failed to send email');
      }
    } catch (error) {
      toast({
        title: 'Error sending email',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSendingEmail(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* Filters */}
      <HStack spacing={4} wrap="wrap">
        <FormControl maxW="250px">
          <FormLabel color="gray.300" fontSize="sm">Search Email</FormLabel>
          <Input
            placeholder="Search by email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            bg="gray.800"
            color="white"
            borderColor="gray.600"
          />
        </FormControl>

        <FormControl maxW="250px">
          <FormLabel color="gray.300" fontSize="sm">Search Name</FormLabel>
          <Input
            placeholder="Search by name..."
            value={searchName}
            onChange={(e) => setSearchName(e.target.value)}
            bg="gray.800"
            color="white"
            borderColor="gray.600"
          />
        </FormControl>

        <FormControl maxW="200px">
          <FormLabel color="gray.300" fontSize="sm">Status</FormLabel>
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            bg="gray.800"
            color="white"
            borderColor="gray.600"
          >
            <option value="all">All Statuses</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="FORCE_CHANGE_PASSWORD">Force Change Password</option>
            <option value="UNCONFIRMED">Unconfirmed</option>
          </Select>
        </FormControl>

        <FormControl maxW="200px">
          <FormLabel color="gray.300" fontSize="sm">Role</FormLabel>
          <Select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            bg="gray.800"
            color="white"
            borderColor="gray.600"
          >
            <option value="all">All Roles</option>
            {roles.map(role => (
              <option key={role.name} value={role.name}>{role.name}</option>
            ))}
          </Select>
        </FormControl>

        <Button
          colorScheme="orange"
          leftIcon={<AddIcon />}
          onClick={openCreateModal}
          alignSelf="flex-end"
        >
          Create User
        </Button>
      </HStack>

      {/* Users Table */}
      <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th color="gray.400" cursor="pointer" onClick={() => handleSort('email')}>
                Email {sortField === 'email' && (sortDirection === 'asc' ? '↑' : '↓')}
              </Th>
              <Th color="gray.400" cursor="pointer" onClick={() => handleSort('name')}>
                Name {sortField === 'name' && (sortDirection === 'asc' ? '↑' : '↓')}
              </Th>
              <Th color="gray.400" cursor="pointer" onClick={() => handleSort('status')}>
                Status {sortField === 'status' && (sortDirection === 'asc' ? '↑' : '↓')}
              </Th>
              <Th color="gray.400">Roles</Th>
              <Th color="gray.400">Tenants</Th>
              <Th color="gray.400" cursor="pointer" onClick={() => handleSort('created')}>
                Created {sortField === 'created' && (sortDirection === 'asc' ? '↑' : '↓')}
              </Th>
            </Tr>
          </Thead>
          <Tbody>
            {filteredAndSortedUsers.map(user => (
              <Tr key={user.username}>
                <Td 
                  color="orange.400" 
                  cursor="pointer" 
                  textDecoration="underline"
                  _hover={{ color: 'orange.300' }}
                  onClick={() => openDetailsModal(user)}
                >
                  {user.email}
                </Td>
                <Td color="white">{user.name || '-'}</Td>
                <Td>
                  <Badge colorScheme={user.enabled ? 'green' : 'red'}>
                    {user.status}
                  </Badge>
                </Td>
                <Td>
                  <HStack spacing={1} wrap="wrap">
                    {user.groups.map(group => (
                      <Badge key={group} colorScheme="blue" fontSize="xs">
                        {group}
                      </Badge>
                    ))}
                  </HStack>
                </Td>
                <Td>
                  <HStack spacing={1} wrap="wrap">
                    {user.tenants.map(t => (
                      <Badge key={t} colorScheme="purple" fontSize="xs">
                        {t}
                      </Badge>
                    ))}
                  </HStack>
                </Td>
                <Td color="gray.400" fontSize="sm">
                  {new Date(user.created).toLocaleDateString()}
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>

        {filteredAndSortedUsers.length === 0 && (
          <Text color="gray.400" textAlign="center" py={8}>
            No users found
          </Text>
        )}
      </Box>

      {/* Create/Edit/Details User Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="orange.400">
            {modalMode === 'create' && 'Create New User'}
            {modalMode === 'edit' && 'Edit User'}
            {modalMode === 'details' && 'User Details'}
          </ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            {modalMode === 'details' && selectedUser ? (
              <VStack spacing={4} align="stretch">
                {/* User Information */}
                <Box bg="gray.700" p={4} borderRadius="md">
                  <VStack spacing={3} align="stretch">
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">Email:</Text>
                      <Text color="white" fontWeight="bold">{selectedUser.email}</Text>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">Name:</Text>
                      <Text color="white">{selectedUser.name || '-'}</Text>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">Status:</Text>
                      <Badge colorScheme={selectedUser.enabled ? 'green' : 'red'}>
                        {selectedUser.status}
                      </Badge>
                    </HStack>
                    <HStack justify="space-between">
                      <Text color="gray.400" fontSize="sm">Created:</Text>
                      <Text color="white" fontSize="sm">
                        {new Date(selectedUser.created).toLocaleString()}
                      </Text>
                    </HStack>
                  </VStack>
                </Box>

                {/* Roles */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>Roles:</Text>
                  <HStack spacing={2} wrap="wrap">
                    {selectedUser.groups.map(group => (
                      <Badge key={group} colorScheme="blue">
                        {group}
                      </Badge>
                    ))}
                  </HStack>
                </Box>

                {/* Tenants */}
                <Box>
                  <Text color="gray.300" fontWeight="bold" mb={2}>Tenants:</Text>
                  <HStack spacing={2} wrap="wrap">
                    {selectedUser.tenants.map(t => (
                      <Badge key={t} colorScheme="purple">
                        {t}
                      </Badge>
                    ))}
                  </HStack>
                </Box>

                {/* Send Email Section */}
                <Box bg="gray.700" p={4} borderRadius="md" borderWidth="1px" borderColor="orange.500">
                  <Text color="orange.400" fontWeight="bold" mb={3}>Send Email</Text>
                  <VStack spacing={3}>
                    <FormControl>
                      <FormLabel color="gray.300" fontSize="sm">Email Template</FormLabel>
                      <Select
                        value={selectedEmailTemplate}
                        onChange={(e) => setSelectedEmailTemplate(e.target.value)}
                        bg="gray.600"
                        color="white"
                        borderColor="gray.500"
                      >
                        {emailTemplates.map(template => (
                          <option key={template.template_type} value={template.template_type}>
                            {template.display_name}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                    <Button
                      colorScheme="orange"
                      width="full"
                      onClick={handleSendEmail}
                      isLoading={sendingEmail}
                    >
                      Send Email
                    </Button>
                  </VStack>
                </Box>

                {/* Action Buttons */}
                <Box borderTop="1px" borderColor="gray.700" pt={4} mt={4}>
                  <HStack spacing={2} justify="flex-start">
                    <Button
                      colorScheme="blue"
                      variant="ghost"
                      leftIcon={<EditIcon />}
                      onClick={() => {
                        onClose();
                        setTimeout(() => openEditModal(selectedUser), 100);
                      }}
                      color="blue.400"
                    >
                      Edit User
                    </Button>
                    <Button
                      colorScheme={selectedUser.enabled ? 'yellow' : 'green'}
                      variant="ghost"
                      onClick={() => {
                        handleToggleUserStatus(selectedUser, !selectedUser.enabled);
                        onClose();
                      }}
                      color={selectedUser.enabled ? 'yellow.400' : 'green.400'}
                    >
                      {selectedUser.enabled ? 'Disable' : 'Enable'}
                    </Button>
                    <Button
                      colorScheme="red"
                      variant="ghost"
                      onClick={() => {
                        onClose();
                        setTimeout(() => handleDeleteUser(selectedUser), 100);
                      }}
                      color="red.400"
                    >
                      Delete
                    </Button>
                  </HStack>
                </Box>
              </VStack>
            ) : (
              <VStack spacing={4}>
              {modalMode === 'create' && (
                <>
                  <FormControl isRequired>
                    <FormLabel color="gray.300">Email</FormLabel>
                    <Input
                      type="email"
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                    />
                  </FormControl>

                  <FormControl>
                    <FormLabel color="gray.300">Display Name</FormLabel>
                    <Input
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                    />
                  </FormControl>

                  <FormControl isRequired>
                    <FormLabel color="gray.300">Temporary Password</FormLabel>
                    <Input
                      type="password"
                      value={newUserPassword}
                      onChange={(e) => setNewUserPassword(e.target.value)}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                      placeholder="Min 8 characters"
                    />
                  </FormControl>
                </>
              )}

              {modalMode === 'edit' && (
                <FormControl>
                  <FormLabel color="gray.300">Display Name</FormLabel>
                  <Input
                    value={editUserName}
                    onChange={(e) => setEditUserName(e.target.value)}
                    bg="gray.700"
                    color="white"
                    borderColor="gray.600"
                  />
                </FormControl>
              )}

              <FormControl>
                <FormLabel color="gray.300">Roles</FormLabel>
                <Stack spacing={2} bg="gray.700" p={3} borderRadius="md">
                  {roles.map(role => (
                    <Checkbox
                      key={role.name}
                      isChecked={selectedRoles.includes(role.name)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedRoles([...selectedRoles, role.name]);
                        } else {
                          setSelectedRoles(selectedRoles.filter(r => r !== role.name));
                        }
                      }}
                      colorScheme="orange"
                      color="white"
                    >
                      <VStack align="start" spacing={0}>
                        <Text fontWeight="bold">{role.name}</Text>
                        {role.description && (
                          <Text fontSize="xs" color="gray.400">{role.description}</Text>
                        )}
                      </VStack>
                    </Checkbox>
                  ))}
                </Stack>
              </FormControl>
            </VStack>
            )}
          </ModalBody>

          {modalMode !== 'details' && (
            <ModalFooter>
              <Button variant="ghost" mr={3} onClick={onClose} color="white">
                Cancel
              </Button>
              <Button
                colorScheme="orange"
                onClick={modalMode === 'create' ? handleCreateUser : handleUpdateUser}
                isLoading={actionLoading}
              >
                {modalMode === 'create' ? 'Create User' : 'Update User'}
              </Button>
            </ModalFooter>
          )}
          {modalMode === 'details' && (
            <ModalFooter>
              <Button variant="ghost" onClick={onClose} color="white">
                Close
              </Button>
            </ModalFooter>
          )}
        </ModalContent>
      </Modal>
    </VStack>
  );
}
