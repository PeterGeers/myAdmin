/**
 * TenantTable Component
 *
 * Filterable/sortable/paginated tenant table for the SysAdmin page.
 * Row-click opens the edit modal.
 */

import React from 'react';
import {
  Box, HStack, Text, Badge, Table, Thead, Tbody, Tr, Td,
  Select, IconButton,
} from '@chakra-ui/react';
import { ChevronLeftIcon, ChevronRightIcon } from '@chakra-ui/icons';
import { FilterableHeader } from '../filters/FilterableHeader';
import type { Tenant } from '../../services/sysadminService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TenantTableProps {
  tenants: Tenant[];
  filters: Record<string, string>;
  setFilter: (field: string, value: string) => void;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSort: (field: string) => void;
  onRowClick: (tenant: Tenant) => void;
  // Pagination
  currentPage: number;
  totalPages: number;
  perPage: number;
  onPageChange: (page: number) => void;
  onPerPageChange: (perPage: number) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const getStatusColor = (status: string) => {
  switch (status) {
    case 'active': return 'green';
    case 'suspended': return 'orange';
    case 'inactive': return 'gray';
    case 'deleted': return 'red';
    default: return 'gray';
  }
};

const getModuleBadgeColor = (module: string) => {
  switch (module) {
    case 'FIN': return 'blue';
    case 'STR': return 'purple';
    case 'ADMIN': return 'orange';
    case 'TENADMIN': return 'teal';
    default: return 'gray';
  }
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const TenantTable: React.FC<TenantTableProps> = ({
  tenants,
  filters,
  setFilter,
  sortBy,
  sortOrder,
  onSort,
  onRowClick,
  currentPage,
  totalPages,
  perPage,
  onPageChange,
  onPerPageChange,
  t,
}) => {
  const getSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortBy === field ? sortOrder : null;

  return (
    <>
      <Box bg="gray.800" borderRadius="md" overflowX="auto">
        <Table variant="simple">
          <Thead>
            <Tr>
              <FilterableHeader
                label={t('tenantManagement.table.administration')}
                filterValue={filters.administration}
                onFilterChange={(v) => setFilter('administration', v)}
                sortable
                sortDirection={getSortDirection('administration')}
                onSort={() => onSort('administration')}
              />
              <FilterableHeader
                label={t('tenantManagement.table.displayName')}
                filterValue={filters.display_name}
                onFilterChange={(v) => setFilter('display_name', v)}
                sortable
                sortDirection={getSortDirection('display_name')}
                onSort={() => onSort('display_name')}
              />
              <FilterableHeader
                label={t('tenantManagement.table.status')}
                filterValue={filters.status}
                onFilterChange={(v) => setFilter('status', v)}
                sortable
                sortDirection={getSortDirection('status')}
                onSort={() => onSort('status')}
              />
              <FilterableHeader
                label={t('tenantManagement.table.modules')}
                filterValue={filters.enabled_modules}
                onFilterChange={(v) => setFilter('enabled_modules', v)}
              />
              <FilterableHeader
                label={t('tenantManagement.table.users')}
                filterValue={filters.user_count}
                onFilterChange={(v) => setFilter('user_count', v)}
              />
              <FilterableHeader
                label={t('tenantManagement.table.created')}
                filterValue={filters.created_at}
                onFilterChange={(v) => setFilter('created_at', v)}
                sortable
                sortDirection={getSortDirection('created_at')}
                onSort={() => onSort('created_at')}
              />
            </Tr>
          </Thead>
          <Tbody>
            {tenants.map((tenant) => (
              <Tr
                key={tenant.administration}
                _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                onClick={() => onRowClick(tenant)}
              >
                <Td color="orange.400" fontWeight="bold">
                  {tenant.administration}
                </Td>
                <Td color="gray.300">{tenant.display_name}</Td>
                <Td>
                  <Badge colorScheme={getStatusColor(tenant.status)}>
                    {tenant.status}
                  </Badge>
                </Td>
                <Td>
                  <HStack spacing={1}>
                    {tenant.enabled_modules.map(module => (
                      <Badge key={module} colorScheme={getModuleBadgeColor(module)} fontSize="xs">
                        {module}
                      </Badge>
                    ))}
                  </HStack>
                </Td>
                <Td color="gray.400">{tenant.user_count}</Td>
                <Td color="gray.400" fontSize="sm">
                  {new Date(tenant.created_at).toLocaleDateString()}
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Box>

      {/* Pagination */}
      <HStack justify="space-between">
        <HStack>
          <Text color="gray.400" fontSize="sm">{t('tenantManagement.rowsPerPage')}:</Text>
          <Select
            value={perPage}
            onChange={(e) => onPerPageChange(Number(e.target.value))}
            bg="gray.600"
            color="white"
            borderColor="gray.500"
            size="sm"
            maxW="80px"
          >
            <option style={{ background: '#2D3748', color: 'white' }} value="5">5</option>
            <option style={{ background: '#2D3748', color: 'white' }} value="10">10</option>
            <option style={{ background: '#2D3748', color: 'white' }} value="25">25</option>
            <option style={{ background: '#2D3748', color: 'white' }} value="50">50</option>
          </Select>
        </HStack>
        <HStack>
          <Text color="gray.400" fontSize="sm">
            {t('tenantManagement.page')} {currentPage} {t('tenantManagement.of')} {totalPages}
          </Text>
          <IconButton
            aria-label={t('tenantManagement.actions.previousPage')}
            icon={<ChevronLeftIcon />}
            size="sm"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            isDisabled={currentPage === 1}
          />
          <IconButton
            aria-label={t('tenantManagement.actions.nextPage')}
            icon={<ChevronRightIcon />}
            size="sm"
            onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
            isDisabled={currentPage === totalPages}
          />
        </HStack>
      </HStack>
    </>
  );
};
