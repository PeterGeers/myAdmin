/**
 * Email Log Panel
 *
 * Shared component for viewing email delivery logs.
 * - SysAdmin mode: shows all tenants, no tenant filter
 * - Tenant Admin mode: shows only current tenant's logs
 *
 * Uses Table Filter Framework v2 (useFilterableTable + FilterableHeader)
 * for consistent filtering, sorting, debounce, and accessibility.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, VStack, HStack, Table, Thead, Tbody, Tr, Th, Td,
  Badge, Select, Button, Text, Spinner,
  Alert, AlertIcon,
} from '@chakra-ui/react';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenant } from '../../context/TenantContext';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { FilterableHeader } from '../filters/FilterableHeader';

interface EmailLogEntry {
  id: number;
  recipient: string;
  email_type: string;
  administration: string;
  status: string;
  ses_message_id: string;
  subject: string;
  sent_by: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface EmailLogPanelProps {
  mode: 'sysadmin' | 'tenant';
}

const STATUS_COLORS: Record<string, string> = {
  sent: 'blue',
  delivered: 'green',
  bounced: 'red',
  complained: 'orange',
  failed: 'red',
};

const TYPE_LABELS: Record<string, string> = {
  invitation: '📨 Invitation',
  tenant_added: '🏢 Tenant Added',
  password_reset: '🔑 Password Reset',
  account_update: '👤 Account Update',
};

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleString('nl-NL', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function EmailLogPanel({ mode }: EmailLogPanelProps) {
  const [logs, setLogs] = useState<EmailLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [limit, setLimit] = useState(100);
  const { currentTenant } = useTenant();

  // Build initial filters — include administration column for sysadmin mode
  const INITIAL_FILTERS = useMemo(() => {
    const base: Record<string, string> = {
      recipient: '',
      email_type: '',
      subject: '',
      sent_by: '',
      status: '',
    };
    if (mode === 'sysadmin') {
      base.administration = '';
    }
    return base;
  }, [mode]);

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<EmailLogEntry>(logs, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'created_at', direction: 'desc' },
  });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (mode === 'tenant' && currentTenant) {
        params.set('administration', currentTenant);
      }

      const response = await authenticatedGet(
        buildEndpoint(`/api/email-log?${params.toString()}`)
      );
      const data = await response.json();

      if (data.success) {
        setLogs(data.logs || []);
      } else {
        setError(data.error || 'Failed to load email logs');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [limit, mode, currentTenant]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <VStack spacing={4} align="stretch">
      {/* Controls: Limit selector + Refresh */}
      <HStack spacing={4} flexWrap="wrap">
        <Select
          maxW="140px" value={String(limit)}
          onChange={(e) => setLimit(Number(e.target.value))}
          bg="gray.800" color="white" borderColor="gray.600"
        >
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="250">250</option>
          <option value="500">500</option>
        </Select>
        <Button colorScheme="orange" size="sm" onClick={fetchLogs}>
          Refresh
        </Button>
      </HStack>

      {error && (
        <Alert status="error"><AlertIcon />{error}</Alert>
      )}

      {loading ? (
        <Box textAlign="center" py={8}>
          <Spinner size="lg" color="orange.400" />
        </Box>
      ) : logs.length === 0 ? (
        <Text color="gray.400" textAlign="center" py={8}>
          No email logs found.
        </Text>
      ) : (
        <Box overflowX="auto" bg="gray.800" borderRadius="md" p={4}>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <FilterableHeader
                  label="Date"
                  sortable
                  sortDirection={sortField === 'created_at' ? sortDirection : null}
                  onSort={() => handleSort('created_at')}
                />
                <FilterableHeader
                  label="Recipient"
                  filterValue={filters.recipient}
                  onFilterChange={(v) => setFilter('recipient', v)}
                  sortable
                  sortDirection={sortField === 'recipient' ? sortDirection : null}
                  onSort={() => handleSort('recipient')}
                />
                <FilterableHeader
                  label="Type"
                  filterValue={filters.email_type}
                  onFilterChange={(v) => setFilter('email_type', v)}
                  sortable
                  sortDirection={sortField === 'email_type' ? sortDirection : null}
                  onSort={() => handleSort('email_type')}
                />
                {mode === 'sysadmin' && (
                  <FilterableHeader
                    label="Tenant"
                    filterValue={filters.administration}
                    onFilterChange={(v) => setFilter('administration', v)}
                    sortable
                    sortDirection={sortField === 'administration' ? sortDirection : null}
                    onSort={() => handleSort('administration')}
                  />
                )}
                <FilterableHeader
                  label="Subject"
                  filterValue={filters.subject}
                  onFilterChange={(v) => setFilter('subject', v)}
                  sortable
                  sortDirection={sortField === 'subject' ? sortDirection : null}
                  onSort={() => handleSort('subject')}
                />
                <FilterableHeader
                  label="Status"
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  sortable
                  sortDirection={sortField === 'status' ? sortDirection : null}
                  onSort={() => handleSort('status')}
                />
                <FilterableHeader
                  label="Sent by"
                  filterValue={filters.sent_by}
                  onFilterChange={(v) => setFilter('sent_by', v)}
                  sortable
                  sortDirection={sortField === 'sent_by' ? sortDirection : null}
                  onSort={() => handleSort('sent_by')}
                />
                <Th color="gray.400" bg="gray.700">Error</Th>
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map((log) => (
                <Tr key={log.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}>
                  <Td color="gray.300" whiteSpace="nowrap">{formatDate(log.created_at)}</Td>
                  <Td color="gray.300">{log.recipient}</Td>
                  <Td color="gray.300">{TYPE_LABELS[log.email_type] || log.email_type}</Td>
                  {mode === 'sysadmin' && <Td color="gray.300">{log.administration}</Td>}
                  <Td color="gray.300" maxW="250px" isTruncated>{log.subject}</Td>
                  <Td>
                    <Badge colorScheme={STATUS_COLORS[log.status] || 'gray'}>
                      {log.status}
                    </Badge>
                  </Td>
                  <Td color="gray.300">{log.sent_by || '—'}</Td>
                  <Td color="red.300" maxW="200px" isTruncated>
                    {log.error_message || ''}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <Text color="gray.500" fontSize="sm">
        Showing {processedData.length} of {logs.length} log(s)
      </Text>
    </VStack>
  );
}
