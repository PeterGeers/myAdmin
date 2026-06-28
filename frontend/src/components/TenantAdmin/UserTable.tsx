/**
 * UserTable Component
 *
 * Filterable/sortable user table for the TenantAdmin UserManagement page.
 * Row-click opens details modal (BankingProcessor pattern).
 */

import React from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Td, Badge, HStack, Text,
} from '@chakra-ui/react';
import { FilterableHeader } from '../filters/FilterableHeader';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  username: string;
  email: string;
  name?: string;
  status: string;
  enabled: boolean;
  groups: string[];
  tenants: string[];
  created: string;
}

interface UserTableProps {
  users: User[];
  filters: Record<string, string>;
  setFilter: (field: string, value: string) => void;
  sortField: string | null;
  sortDirection: 'asc' | 'desc';
  handleSort: (field: string) => void;
  onRowClick: (user: User) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const UserTable: React.FC<UserTableProps> = ({
  users,
  filters,
  setFilter,
  sortField,
  sortDirection,
  handleSort,
  onRowClick,
  t,
}) => {
  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  return (
    <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            <FilterableHeader
              label={t('userManagement.table.email')}
              filterValue={filters.email}
              onFilterChange={(v) => setFilter('email', v)}
              sortable
              sortDirection={columnSortDirection('email')}
              onSort={() => handleSort('email')}
            />
            <FilterableHeader
              label={t('userManagement.table.name')}
              filterValue={filters.name}
              onFilterChange={(v) => setFilter('name', v)}
              sortable
              sortDirection={columnSortDirection('name')}
              onSort={() => handleSort('name')}
            />
            <FilterableHeader
              label={t('userManagement.table.status')}
              filterValue={filters.status}
              onFilterChange={(v) => setFilter('status', v)}
              sortable
              sortDirection={columnSortDirection('status')}
              onSort={() => handleSort('status')}
            />
            <FilterableHeader
              label={t('userManagement.table.roles')}
              filterValue={filters.groups}
              onFilterChange={(v) => setFilter('groups', v)}
            />
            <FilterableHeader
              label={t('userManagement.table.created')}
              filterValue={filters.created}
              onFilterChange={(v) => setFilter('created', v)}
              sortable
              sortDirection={columnSortDirection('created')}
              onSort={() => handleSort('created')}
            />
            <FilterableHeader
              label={t('userManagement.table.tenants')}
              filterValue={filters.tenants}
              onFilterChange={(v) => setFilter('tenants', v)}
            />
          </Tr>
        </Thead>
        <Tbody>
          {users.map(user => (
            <Tr
              key={user.username}
              _hover={{ bg: 'gray.700', cursor: 'pointer' }}
              onClick={() => onRowClick(user)}
            >
              <Td color="orange.400" fontWeight="bold">
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
              <Td color="gray.400" fontSize="sm">
                {new Date(user.created).toLocaleDateString()}
              </Td>
              <Td>
                <HStack spacing={1} wrap="wrap">
                  {user.tenants.map(tenantName => (
                    <Badge key={tenantName} colorScheme="purple" fontSize="xs">
                      {tenantName}
                    </Badge>
                  ))}
                </HStack>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>

      {users.length === 0 && (
        <Text color="gray.400" textAlign="center" py={8}>
          {t('userManagement.table.noUsers')}
        </Text>
      )}
    </Box>
  );
};
