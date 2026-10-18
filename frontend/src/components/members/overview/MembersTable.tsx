/**
 * Members Overview — the Chakra table (header map + cell map over the unified
 * column model, plus the selection column). Extracted from
 * `pages/MembersPage.tsx` during the file-length split (code-quality-fixes
 * 2026-10-15, task 6) with ZERO behaviour change: the loading spinner, the
 * `overflowX="auto"` wrapper, the FilterableHeader wiring, the row-click +
 * per-row selection, and the empty-state row are moved verbatim. All state +
 * handlers are owned by the page and passed in as props.
 */

import React from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Th, Td, HStack, Text, Spinner, Checkbox,
} from '@chakra-ui/react';
import { FilterableHeader } from '../../filters/FilterableHeader';
import type { OverviewColumn } from './membersOverviewModel';
import type { MemberRow, FieldConfigField } from '../../../types/members';

export interface MembersTableProps {
  loading: boolean;
  columns: OverviewColumn[];
  visibleData: MemberRow[];
  colSpan: number;
  columnLabel: (field: FieldConfigField) => string;
  renderCell: (field: FieldConfigField, row: MemberRow) => React.ReactNode;
  isFilterable: (key: string) => boolean;
  filters: Record<string, string>;
  setFilter: (key: string, value: string) => void;
  columnSortDirection: (field: string) => 'asc' | 'desc' | null;
  handleSort: (field: string) => void;
  allVisibleSelected: boolean;
  someVisibleSelected: boolean;
  toggleSelectAll: () => void;
  selectedIds: Set<string>;
  toggleRow: (id: string) => void;
  onRowClick: (row: MemberRow) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

export const MembersTable: React.FC<MembersTableProps> = ({
  loading,
  columns,
  visibleData,
  colSpan,
  columnLabel,
  renderCell,
  isFilterable,
  filters,
  setFilter,
  columnSortDirection,
  handleSort,
  allVisibleSelected,
  someVisibleSelected,
  toggleSelectAll,
  selectedIds,
  toggleRow,
  onRowClick,
  t,
}) => {
  if (loading) {
    return (
      <HStack color="white"><Spinner color="orange.300" /><Text>{t('table.loading')}</Text></HStack>
    );
  }

  return (
    <Box overflowX="auto">
      <Table variant="simple" size="sm" bg="gray.800" color="white">
        <Thead>
          <Tr>
            {/* Unified column model (design C3): ONE header map over
                `columns = [member_number] ⊕ chosenColumns`. member_number
                always leads (R7.1). Every column gets identical
                FilterableHeader wiring (filter + sort), the filter input
                gated by `isFilterable` (context `filterable_columns`, C6). */}
            {columns.map(({ field }) => (
              <FilterableHeader
                key={field.key}
                label={columnLabel(field)}
                filterValue={isFilterable(field.key) ? (filters[field.key] ?? '') : undefined}
                onFilterChange={
                  isFilterable(field.key) ? (v) => setFilter(field.key, v) : undefined
                }
                placeholder={t('filters.placeholder')}
                sortable
                sortDirection={columnSortDirection(field.key)}
                onSort={() => handleSort(field.key)}
              />
            ))}
            {/* Selection column (task 20.4) — LAST so the existing column
                order (name first) is preserved. Header carries select-all. */}
            <Th textAlign="center">
              <Checkbox
                colorScheme="orange"
                aria-label={t('selection.selectAll')}
                isChecked={allVisibleSelected}
                isIndeterminate={someVisibleSelected}
                onChange={toggleSelectAll}
              />
            </Th>
          </Tr>
        </Thead>
        <Tbody>
          {visibleData.map(row => (
            <Tr
              key={row.member_id}
              _hover={{ bg: 'gray.700', cursor: 'pointer' }}
              onClick={() => onRowClick(row)}
            >
              {/* Unified column model (design C3): ONE cell map over the same
                  `columns`, in the same order as the header map. member_number
                  + region keep their legacy accessors; every other column
                  renders through the shared valueFor + renderFieldValue. */}
              {columns.map(({ field }) => (
                <Td key={field.key}>{renderCell(field, row)}</Td>
              ))}
              {/* Per-row selection checkbox (task 20.4). Stop propagation so
                  toggling selection never opens the row-click view modal. */}
              <Td
                textAlign="center"
                onClick={(e) => e.stopPropagation()}
              >
                <Checkbox
                  colorScheme="orange"
                  aria-label={t('selection.selectRow', { name: row.name || row.member_id })}
                  isChecked={selectedIds.has(row.member_id)}
                  onChange={() => toggleRow(row.member_id)}
                />
              </Td>
            </Tr>
          ))}
          {visibleData.length === 0 && (
            <Tr>
              <Td colSpan={colSpan}>
                <Text color="gray.500">{t('table.empty')}</Text>
              </Td>
            </Tr>
          )}
        </Tbody>
      </Table>
    </Box>
  );
};
