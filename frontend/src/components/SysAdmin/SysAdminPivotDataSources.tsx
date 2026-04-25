import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, Spinner,
  Table, Thead, Tbody, Tr, Td,
  Switch, Select, Input, useToast, Alert, AlertIcon,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { authenticatedGet, authenticatedPut } from '../../services/apiService';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';

/** Shape of a single data source returned by the API */
interface DataSource {
  name: string;
  type: string;           // "VIEW" or "BASE TABLE"
  pivot_enabled: boolean;
  module: string | null;
  label: string | null;
}

/** Local editable copy — module/label always strings for controlled inputs */
interface EditableSource {
  name: string;
  type: string;
  pivot_enabled: boolean;
  module: string;   // "" | "FIN" | "STR" | "ZZP"
  label: string;
}

const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  type: '',
  module: '',
  label: '',
};

function toEditable(src: DataSource): EditableSource {
  return {
    name: src.name,
    type: src.type,
    pivot_enabled: src.pivot_enabled,
    module: src.module ?? '',
    label: src.label ?? '',
  };
}

export default function SysAdminPivotDataSources() {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [sources, setSources] = useState<EditableSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  // ── Filter + Sort via framework v2 ────────────────────────────────
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<EditableSource>(sources, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'name', direction: 'asc' },
  });

  /** Helper: returns sort direction for a column, or null if not active */
  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ── Fetch ──────────────────────────────────────────────────────────
  const fetchSources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authenticatedGet('/api/sysadmin/pivot/datasources');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      const body = await res.json();
      if (!body.success) throw new Error(body.error || 'Unknown error');
      setSources((body.data as DataSource[]).map(toEditable));
      setDirty(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSources(); }, [fetchSources]);

  // ── Mutations ──────────────────────────────────────────────────────
  const updateSource = (name: string, patch: Partial<EditableSource>) => {
    setSources(prev =>
      prev.map(s => (s.name === name ? { ...s, ...patch } : s)),
    );
    setDirty(true);
  };

  // ── Save ───────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        sources: sources.map(s => ({
          name: s.name,
          pivot_enabled: s.pivot_enabled,
          module: s.module || null,
          label: s.label || null,
        })),
      };
      const res = await authenticatedPut('/api/sysadmin/pivot/datasources', payload);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      const body = await res.json();
      if (!body.success) throw new Error(body.error || 'Unknown error');

      setDirty(false);
      toast({
        title: t('pivotDataSources.messages.saved'),
        status: 'success',
        duration: 3000,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      toast({
        title: t('pivotDataSources.messages.errorSaving'),
        description: msg,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">{t('pivotDataSources.loading')}</Text>
        </VStack>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4}>
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          {t('pivotDataSources.messages.errorLoading')}: {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={4} align="stretch">
        {/* Header row */}
        <HStack justify="space-between" wrap="wrap" spacing={4}>
          <Text color="gray.400" fontSize="sm">
            {t('pivotDataSources.total')}:{' '}
            <Text as="span" color="orange.400" fontWeight="bold">
              {sources.length}
            </Text>
          </Text>

          <Button
            colorScheme="orange"
            size="sm"
            onClick={handleSave}
            isLoading={saving}
            isDisabled={!dirty}
          >
            {t('pivotDataSources.save')}
          </Button>
        </HStack>

        {/* Table */}
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('pivotDataSources.table.name')}
                  filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)}
                  sortable
                  sortDirection={columnSortDirection('name')}
                  onSort={() => handleSort('name')}
                />
                <FilterableHeader
                  label={t('pivotDataSources.table.type')}
                  filterValue={filters.type}
                  onFilterChange={(v) => setFilter('type', v)}
                  sortable
                  sortDirection={columnSortDirection('type')}
                  onSort={() => handleSort('type')}
                />
                <FilterableHeader
                  label={t('pivotDataSources.table.module')}
                  filterValue={filters.module}
                  onFilterChange={(v) => setFilter('module', v)}
                  sortable
                  sortDirection={columnSortDirection('module')}
                  onSort={() => handleSort('module')}
                />
                <FilterableHeader
                  label={t('pivotDataSources.table.label')}
                  filterValue={filters.label}
                  onFilterChange={(v) => setFilter('label', v)}
                  sortable
                  sortDirection={columnSortDirection('label')}
                  onSort={() => handleSort('label')}
                />
                {/* pivot_enabled: sortable but no text filter (boolean toggle column) */}
                <FilterableHeader
                  label={t('pivotDataSources.table.pivotEnabled')}
                  sortable
                  sortDirection={columnSortDirection('pivot_enabled')}
                  onSort={() => handleSort('pivot_enabled')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(src => (
                <Tr key={src.name} _hover={{ bg: 'gray.700' }}>
                  {/* Name */}
                  <Td color="orange.400" fontWeight="medium" fontSize="sm">
                    {src.name}
                  </Td>

                  {/* Type badge */}
                  <Td>
                    <Badge
                      colorScheme={src.type === 'VIEW' ? 'blue' : 'gray'}
                      fontSize="xs"
                    >
                      {src.type}
                    </Badge>
                  </Td>

                  {/* Module dropdown */}
                  <Td>
                    <Select
                      size="xs"
                      maxW="100px"
                      value={src.module}
                      onChange={e => updateSource(src.name, { module: e.target.value })}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                    >
                      <option value="" style={{ background: '#2D3748', color: 'white' }}>—</option>
                      <option value="FIN" style={{ background: '#2D3748', color: 'white' }}>FIN</option>
                      <option value="STR" style={{ background: '#2D3748', color: 'white' }}>STR</option>
                      <option value="ZZP" style={{ background: '#2D3748', color: 'white' }}>ZZP</option>
                    </Select>
                  </Td>

                  {/* Label input */}
                  <Td>
                    <Input
                      size="xs"
                      maxW="220px"
                      value={src.label}
                      placeholder={t('pivotDataSources.table.labelPlaceholder')}
                      onChange={e => updateSource(src.name, { label: e.target.value })}
                      bg="gray.700"
                      color="white"
                      borderColor="gray.600"
                      _placeholder={{ color: 'gray.500' }}
                    />
                  </Td>

                  {/* Pivot enabled toggle */}
                  <Td>
                    <Switch
                      colorScheme="orange"
                      size="sm"
                      isChecked={src.pivot_enabled}
                      onChange={e =>
                        updateSource(src.name, { pivot_enabled: e.target.checked })
                      }
                      aria-label={`${t('pivotDataSources.table.pivotEnabled')} ${src.name}`}
                    />
                  </Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
                <Tr>
                  <Td colSpan={5} textAlign="center" color="gray.500" py={8}>
                    {t('pivotDataSources.noResults')}
                  </Td>
                </Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      </VStack>
    </Box>
  );
}
