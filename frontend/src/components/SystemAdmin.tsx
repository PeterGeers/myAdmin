import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, Button, Table, Thead, Tbody, Tr, Th, Td,
  Badge, useToast, Spinner, Text, Select, AlertDialog,
  AlertDialogBody, AlertDialogFooter, AlertDialogHeader, AlertDialogContent,
  AlertDialogOverlay, useDisclosure
} from '@chakra-ui/react';
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
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [actionLoading, setActionLoading] = useState(false);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [deleteUsername, setDeleteUsername] = useState<string>('');
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  useEffect(() => {
    loadData();
  }, []);

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

  const addUserToGroup = async (username: string, groupName: string) => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/admin/users/${username}/groups`), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ groupName })
      });

      if (response.ok) {
        toast({
          title: 'Success',
          description: `Added ${username} to ${groupName}`,
          status: 'success',
          duration: 3000,
        });
        await loadData();
        setSelectedUser(null);
        setSelectedGroup('');
      } else {
        throw new Error('Failed to add user to group');
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

  const removeUserFromGroup = async (username: string, groupName: string) => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/admin/users/${username}/groups/${groupName}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (response.ok) {
        toast({
          title: 'Success',
          description: `Removed ${username} from ${groupName}`,
          status: 'success',
          duration: 3000,
        });
        await loadData();
      } else {
        throw new Error('Failed to remove user from group');
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

  const toggleUserStatus = async (username: string, enable: boolean) => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const action = enable ? 'enable' : 'disable';
      const response = await fetch(buildApiUrl(`/api/admin/users/${username}/${action}`), {
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

  const confirmDeleteUser = (username: string) => {
    setDeleteUsername(username);
    onOpen();
  };

  const deleteUser = async () => {
    setActionLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(buildApiUrl(`/api/admin/users/${deleteUsername}`), {
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
        onClose();
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
        <Heading color="orange.400" size="xl">User & Role Management</Heading>

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
                  <Tr key={user.username}>
                    <Td color="gray.300">{user.email}</Td>
                    <Td>
                      <Badge colorScheme={user.enabled ? 'green' : 'red'}>
                        {user.status}
                      </Badge>
                    </Td>
                    <Td>
                      <HStack spacing={2} flexWrap="wrap">
                        {user.groups.map((group) => (
                          <Badge key={group} colorScheme="blue" cursor="pointer"
                            onClick={() => removeUserFromGroup(user.username, group)}>
                            {group} ✕
                          </Badge>
                        ))}
                        {selectedUser === user.username ? (
                          <HStack>
                            <Select size="xs" value={selectedGroup} onChange={(e) => setSelectedGroup(e.target.value)}
                              bg="gray.700" color="white" w="150px">
                              <option value="">Select role...</option>
                              {groups.filter(g => !user.groups.includes(g.name)).map((group) => (
                                <option key={group.name} value={group.name}>{group.name}</option>
                              ))}
                            </Select>
                            <Button size="xs" colorScheme="green" onClick={() => addUserToGroup(user.username, selectedGroup)}
                              isDisabled={!selectedGroup || actionLoading}>
                              Add
                            </Button>
                            <Button size="xs" onClick={() => { setSelectedUser(null); setSelectedGroup(''); }}>
                              Cancel
                            </Button>
                          </HStack>
                        ) : (
                          <Button size="xs" colorScheme="orange" onClick={() => setSelectedUser(user.username)}>
                            + Add Role
                          </Button>
                        )}
                      </HStack>
                    </Td>
                    <Td color="gray.400" fontSize="xs">
                      {new Date(user.created).toLocaleDateString()}
                    </Td>
                    <Td>
                      <HStack spacing={2}>
                        <Button size="xs" colorScheme={user.enabled ? 'red' : 'green'}
                          onClick={() => toggleUserStatus(user.username, !user.enabled)}
                          isLoading={actionLoading}>
                          {user.enabled ? 'Disable' : 'Enable'}
                        </Button>
                        <Button size="xs" colorScheme="red" variant="outline"
                          onClick={() => confirmDeleteUser(user.username)}
                          isLoading={actionLoading}>
                          Delete
                        </Button>
                      </HStack>
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

      {/* Delete Confirmation Dialog */}
      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              Delete User
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              Are you sure you want to delete user <strong>{deleteUsername}</strong>? This action cannot be undone.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose}>
                Cancel
              </Button>
              <Button colorScheme="red" onClick={deleteUser} ml={3} isLoading={actionLoading}>
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
