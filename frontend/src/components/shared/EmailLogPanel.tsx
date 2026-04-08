/**
 * Email Log Panel
 *
 * Shared component for viewing email delivery logs.
 * - SysAdmin mode: shows all tenants, no tenant filter
 * - Tenant Admin mode: shows only current tenant's logs
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Table, Thead, Tbody, Tr, Th, Td,
  Badge, Input, Select, Button, Text, Spinner,
  Alert, AlertIcon, InputGroup, InputLeftElement,
} from '@chakra-ui/react';
import { SearchIcon } from '@chakra-ui/icons';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';

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
  const [recipientFilter, setRecipientFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [limit, setLimit] = useState(100);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (recipientFilter) params.set('recipient', recipientFilter);

      const response = await authenticatedGet(
        buildEndpoint(`/api/email-log?${params.toString()}`)
      );
      const data = await response.json();

      if (data.success) {
        let filtered = data.logs || [];
        if (statusFilter) {
          filtered = filtered.filter((l: EmailLogEntry) => l.status === statusFilter);
        }
        setLogs(filtered);
      } else {
        setError(data.error || 'Failed to load email logs');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [recipientFilter, statusFilter, limit]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <VStack spacing={4} align="stretch">
      {/* Filters */}
      <HStack spacing={4} flexWrap="wrap">
        <InputGroup maxW="300px">
          <InputLeftElement pointerEvents="none">
            <SearchIcon color="gray.500" />
          </InputLeftElement>
          <Input
            placeholder="Filter by email..."
            value={recipientFilter}
            onChange={(e) => setRecipientFilter(e.target.value)}
            bg="gray.800" color="white" borderColor="gray.600"
            onKeyDown={(e) => e.key === 'Enter' && fetchLogs()}
          />
        </InputGroup>
        <Select
          maxW="180px" value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          bg="gray.800" color="white" borderColor="gray.600"
        >
          <option value="">All statuses</option>
          <option value="sent">Sent</option>
          <option value="delivered">Delivered</option>
          <option value="bounced">Bounced</option>
          <option value="complained">Complained</option>
          <option value="failed">Failed</option>
        </Select>
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
        <Box overflowX="auto">
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="gray.400">Date</Th>
                <Th color="gray.400">Recipient</Th>
                <Th color="gray.400">Type</Th>
                {mode === 'sysadmin' && <Th color="gray.400">Tenant</Th>}
                <Th color="gray.400">Subject</Th>
                <Th color="gray.400">Status</Th>
                <Th color="gray.400">Sent by</Th>
                <Th color="gray.400">Error</Th>
              </Tr>
            </Thead>
            <Tbody>
              {logs.map((log) => (
                <Tr key={log.id} _hover={{ bg: 'gray.800' }}>
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
        Showing {logs.length} log(s)
      </Text>
    </VStack>
  );
}
