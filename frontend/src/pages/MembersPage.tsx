/**
 * Members Overview page (Leden Overzicht) — Chakra Table with shared filters,
 * sort, a compact/full view switch driven by the resolved field config, a
 * read-only subgroup/region Badge column, and a row-click view modal.
 *
 * COMPOSES the shared toolkit (R7.9) — it does NOT rebuild it:
 * - Dark theme + header-right orange primary actions (BankingProcessor /
 *   ZZPInvoices pattern, `32-frontend-ui.md`): no per-row buttons; a row click
 *   opens the read-only view modal.
 * - Chakra `Table variant="simple"` on `bg="gray.800"`, sortable headers, hover
 *   rows, responsive `overflowX="auto"`.
 * - Filtering + sorting via the Table Filter Framework v2
 *   (`FilterableHeader` + `useFilterableTable` → `useColumnFilters` /
 *   `useTableSort`) for region/status/type.
 * - Rows from `GET /members`; field config from `GET /members/field-config`
 *   drives the compact/full view switch (fixed ⊕ overlay columns).
 *
 * Subgroup filtering is enforced by the module edge (R8.7): the page renders
 * whatever `GET /members` returns and never invents scope client-side.
 *
 * The read-only view modal (task 19.1) is included here since it completes the
 * "clickable" definition. The edit/add/delete/transition modals are Phase 6
 * (tasks 19–20) and are intentionally NOT built here.
 *
 * Export (task 20.2, R8.4): a header-right "Exporteren" action produces a CSV of
 * the currently-loaded, scope-filtered rows using the shared
 * `frontend/src/utils/csvExport.ts` helper. We export the client-side rows (not a
 * second `GET /members/export` round-trip) because those rows already came from
 * the scoped `GET /members`, so the CSV inherently respects scope (R8.7) and
 * reflects any active column filter — never inventing scope client-side.
 *
 * Reference: `frontend/src/pages/ZZPInvoices.tsx`, `.kiro/steering/32-frontend-ui.md`.
 *
 * _Requirements: R7.5, R7.6, R7.9, R8.4, R8.7_
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, HStack, ButtonGroup, Badge, Checkbox, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, RepeatIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { listMembers, getMember, getFieldConfig } from '../services/membersApiService';
import { MembersAddModal } from '../components/members/MembersAddModal';
import { MembersEditModal } from '../components/members/MembersEditModal';
import { MembersDeleteConfirm } from '../components/members/MembersDeleteConfirm';
import { MembersTransitionModal } from '../components/members/MembersTransitionModal';
import { MembersBulkTransitionModal } from '../components/members/MembersBulkTransitionModal';
import { generateCsv, downloadCsv } from '../utils/csvExport';
import type {
  Member, MemberRow, FieldConfig, FieldConfigField, LocalizedLabel,
} from '../types/members';

/** The always-visible (compact) fixed columns, in display order. */
const COMPACT_FIELD_KEYS = ['name', 'email', 'status', 'membership_type'] as const;

/** Column filter keys — region/status/type plus the compact fixed fields. */
const INITIAL_FILTERS: Record<string, string> = {
  name: '',
  email: '',
  status: '',
  membership_type: '',
  region: '',
};

/** Resolve a possibly-localized label to a plain string for the current lang. */
function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

const MembersPage: React.FC = () => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const lang = (i18n?.language || 'nl').slice(0, 2);

  const [members, setMembers] = useState<Member[]>([]);
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  const [loading, setLoading] = useState(true);

  // Compact/full view switch (driven by field config: fixed ⊕ overlay columns).
  const [viewMode, setViewMode] = useState<'compact' | 'full'>('compact');

  // Read-only view modal (task 19.1).
  const { isOpen: isViewOpen, onOpen: onViewOpen, onClose: onViewClose } = useDisclosure();
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Add / application modal (task 20.1).
  const { isOpen: isAddOpen, onOpen: onAddOpen, onClose: onAddClose } = useDisclosure();

  // Edit modal (task 19.2) + delete confirm (task 19.3) — both act on the
  // currently-selected member (opened from the read-only view modal footer).
  const { isOpen: isEditOpen, onOpen: onEditOpen, onClose: onEditClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();

  // Single transition modal (task 20.3, R8.5) — acts on the selected member;
  // opened from the read-only view modal footer.
  const {
    isOpen: isTransitionOpen, onOpen: onTransitionOpen, onClose: onTransitionClose,
  } = useDisclosure();

  // Bulk transition modal (task 20.4, R8.6) — acts over the checkbox-selected rows.
  const {
    isOpen: isBulkOpen, onOpen: onBulkOpen, onClose: onBulkClose,
  } = useDisclosure();

  // Row selection for bulk actions (task 20.4): the set of selected member_ids.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const loadMembers = useCallback(async () => {
    try {
      setLoading(true);
      const rows = await listMembers<Member[]>();
      setMembers(Array.isArray(rows) ? rows : []);
    } catch {
      toast({ title: t('table.empty'), status: 'error' });
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [toast, t]);

  useEffect(() => { loadMembers(); }, [loadMembers]);

  useEffect(() => {
    getFieldConfig<FieldConfig>()
      .then(cfg => setFieldConfig(cfg ?? null))
      .catch(() => setFieldConfig(null));
  }, []);

  // Overlay (full-view-only) columns from the resolved field config: any field
  // that is not one of the fixed compact keys and is not the region dimension.
  const overlayFields: FieldConfigField[] = useMemo(() => {
    const fixed = new Set<string>([...COMPACT_FIELD_KEYS, 'region', 'member_id']);
    const fields = fieldConfig?.fields ?? [];
    return fields
      .filter(f => !fixed.has(f.key))
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [fieldConfig]);

  // Build flat rows; promote the region display value for the badge column.
  const memberRows: MemberRow[] = useMemo(
    () => members.map(m => ({
      ...m,
      region_display: (m.region as string) || '',
    })),
    [members],
  );

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<MemberRow>(memberRows, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'name', direction: 'asc' },
  });

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ── Row selection for bulk actions (task 20.4, R8.6) ─────────────────────────
  // The select-all header toggles every VISIBLE (`processedData`) row so the
  // selection tracks the shared filter/sort framework's current view.
  const visibleIds = useMemo(
    () => processedData.map(r => r.member_id),
    [processedData],
  );

  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
  const someVisibleSelected =
    visibleIds.some(id => selectedIds.has(id)) && !allVisibleSelected;

  const toggleSelectAll = useCallback(() => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (visibleIds.every(id => next.has(id))) {
        // All visible already selected → clear them.
        visibleIds.forEach(id => next.delete(id));
      } else {
        visibleIds.forEach(id => next.add(id));
      }
      return next;
    });
  }, [visibleIds]);

  const toggleRow = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const selectedIdList = useMemo(() => Array.from(selectedIds), [selectedIds]);

  // After a successful bulk transition: clear the selection AND refresh the list.
  const handleBulkDone = useCallback(() => {
    clearSelection();
    loadMembers();
  }, [clearSelection, loadMembers]);

  const handleRowClick = useCallback(async (row: MemberRow) => {
    setSelectedMember(row);
    onViewOpen();
    try {
      setDetailLoading(true);
      const full = await getMember<Member>(row.member_id);
      if (full) setSelectedMember(full);
    } catch {
      // Keep the row data already shown; the modal stays usable.
    } finally {
      setDetailLoading(false);
    }
  }, [onViewOpen]);

  const handleViewClose = () => {
    onViewClose();
    setSelectedMember(null);
  };

  // Edit (task 19.2): switch from the read-only view modal to the edit modal on
  // the same selected member. Close the view modal but KEEP `selectedMember` so
  // the edit form can pre-populate from it.
  const handleEditOpen = () => {
    onViewClose();
    onEditOpen();
  };

  const handleEditClose = () => {
    onEditClose();
    setSelectedMember(null);
  };

  // Delete (task 19.3): open the confirm dialog for the selected member. Close
  // the view modal but KEEP `selectedMember` so the confirm can name it.
  const handleDeleteOpen = () => {
    onViewClose();
    onDeleteOpen();
  };

  const handleDeleteClose = () => {
    onDeleteClose();
    setSelectedMember(null);
  };

  // Single transition (task 20.3): switch from the read-only view modal to the
  // transition modal on the same selected member. Close the view modal but KEEP
  // `selectedMember` so the transition modal knows the member + its current state.
  const handleTransitionOpen = () => {
    onViewClose();
    onTransitionOpen();
  };

  const handleTransitionClose = () => {
    onTransitionClose();
    setSelectedMember(null);
  };

  // Export the currently-loaded, scope-filtered rows (R8.4). We serialize
  // `processedData` — the rows after the shared filter/sort framework — so the
  // CSV matches exactly what the user sees and inherently respects scope (R8.7:
  // those rows already came from the scoped `GET /members`). Reuses the shared
  // `csvExport.ts` helper (RFC-4180 escaping + BOM), the same one ZZP/pivot use.
  const handleExport = useCallback(() => {
    try {
      if (processedData.length === 0) {
        toast({ title: t('export.empty'), status: 'info' });
        return;
      }

      // Fixed/meaningful columns first, then any resolved overlay columns.
      const fixedColumns: { key: string; header: string }[] = [
        { key: 'member_id', header: t('modal.fields.memberId') },
        { key: 'name', header: t('columns.name') },
        { key: 'email', header: t('columns.email') },
        { key: 'status', header: t('filters.status') },
        { key: 'membership_type', header: t('columns.membershipType') },
        { key: 'region', header: t('filters.region') },
      ];
      const overlayColumnsDefs = overlayFields.map(f => ({
        key: f.key,
        header: resolveLabel(f.label, lang, f.key),
      }));
      const columns = [...fixedColumns, ...overlayColumnsDefs];

      const headers = columns.map(c => c.header);
      const rows = processedData.map(row => columns.map(c => row[c.key]));
      const csv = generateCsv(headers, rows);

      const stamp = new Date().toISOString().slice(0, 10);
      downloadCsv(csv, `leden-${stamp}.csv`);
    } catch {
      toast({ title: t('export.error'), status: 'error' });
    }
  }, [processedData, overlayFields, lang, t, toast]);

  // Total column count (fixed compact + region + overlay when in full view + the
  // trailing selection column).
  const overlayColumns = viewMode === 'full' ? overlayFields : [];
  const colSpan = COMPACT_FIELD_KEYS.length + 1 + overlayColumns.length + 1;

  return (
    <Box p={6}>
      {/* Header: title + view switch + primary actions (orange) */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('overview.title')}</Text>
        <HStack spacing={3}>
          {/* Compact/full view switch */}
          <ButtonGroup size="sm" isAttached variant="outline">
            <Button
              colorScheme={viewMode === 'compact' ? 'orange' : 'gray'}
              variant={viewMode === 'compact' ? 'solid' : 'ghost'}
              onClick={() => setViewMode('compact')}
            >
              {t('view.compact')}
            </Button>
            <Button
              colorScheme={viewMode === 'full' ? 'orange' : 'gray'}
              variant={viewMode === 'full' ? 'solid' : 'ghost'}
              onClick={() => setViewMode('full')}
            >
              {t('view.full')}
            </Button>
          </ButtonGroup>
          {/* Bulk transition action (task 20.4, R8.6) — appears only when ≥1 row
              is selected; opens the bulk-transition modal over the selection. */}
          {selectedIds.size > 0 && (
            <Button
              size="sm"
              leftIcon={<RepeatIcon />}
              colorScheme="orange"
              variant="ghost"
              onClick={onBulkOpen}
            >
              {t('bulkTransition.barLabel', { count: selectedIds.size })}
            </Button>
          )}
          {/* Export action (task 20.2, R8.4) — right-aligned, ZZP header pattern. */}
          <Button
            size="sm"
            leftIcon={<DownloadIcon />}
            colorScheme="orange"
            variant="ghost"
            onClick={handleExport}
          >
            {t('actions.export')}
          </Button>
          {/* Primary action: add / application (task 20.1, R8.3) — orange, header-right. */}
          <Button
            size="sm"
            leftIcon={<AddIcon />}
            colorScheme="orange"
            onClick={onAddOpen}
          >
            {t('actions.add')}
          </Button>
        </HStack>
      </Flex>

      {loading ? (
        <HStack color="white"><Spinner color="orange.300" /><Text>{t('table.loading')}</Text></HStack>
      ) : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('columns.name')}
                  filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)}
                  placeholder={t('filters.placeholder')}
                  sortable
                  sortDirection={columnSortDirection('name')}
                  onSort={() => handleSort('name')}
                />
                <FilterableHeader
                  label={t('columns.email')}
                  filterValue={filters.email}
                  onFilterChange={(v) => setFilter('email', v)}
                  placeholder={t('filters.placeholder')}
                  sortable
                  sortDirection={columnSortDirection('email')}
                  onSort={() => handleSort('email')}
                />
                <FilterableHeader
                  label={t('filters.status')}
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  placeholder={t('filters.placeholder')}
                  sortable
                  sortDirection={columnSortDirection('status')}
                  onSort={() => handleSort('status')}
                />
                <FilterableHeader
                  label={t('filters.type')}
                  filterValue={filters.membership_type}
                  onFilterChange={(v) => setFilter('membership_type', v)}
                  placeholder={t('filters.placeholder')}
                  sortable
                  sortDirection={columnSortDirection('membership_type')}
                  onSort={() => handleSort('membership_type')}
                />
                <FilterableHeader
                  label={t('filters.region')}
                  filterValue={filters.region}
                  onFilterChange={(v) => setFilter('region', v)}
                  placeholder={t('filters.placeholder')}
                  sortable
                  sortDirection={columnSortDirection('region')}
                  onSort={() => handleSort('region')}
                />
                {overlayColumns.map(f => (
                  <FilterableHeader
                    key={f.key}
                    label={resolveLabel(f.label, lang, f.key)}
                    sortable
                    sortDirection={columnSortDirection(f.key)}
                    onSort={() => handleSort(f.key)}
                  />
                ))}
                {/* Selection column (task 20.4) — LAST so the existing column
                    order (name first) is preserved. Header carries select-all. */}
                <Th textAlign="center">
                  <Checkbox
                    colorScheme="orange"
                    aria-label={t('bulkTransition.selectAll')}
                    isChecked={allVisibleSelected}
                    isIndeterminate={someVisibleSelected}
                    onChange={toggleSelectAll}
                  />
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(row => (
                <Tr
                  key={row.member_id}
                  _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(row)}
                >
                  <Td>{row.name || '-'}</Td>
                  <Td>{row.email || '-'}</Td>
                  <Td>{row.status || '-'}</Td>
                  <Td>{(row.membership_type as string) || '-'}</Td>
                  <Td>
                    {row.region_display
                      ? <Badge colorScheme="purple">{row.region_display}</Badge>
                      : <Text color="gray.500">-</Text>}
                  </Td>
                  {overlayColumns.map(f => (
                    <Td key={f.key}>{String(row[f.key] ?? '-')}</Td>
                  ))}
                  {/* Per-row selection checkbox (task 20.4). Stop propagation so
                      toggling selection never opens the row-click view modal. */}
                  <Td
                    textAlign="center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Checkbox
                      colorScheme="orange"
                      aria-label={t('bulkTransition.selectRow', { name: row.name || row.member_id })}
                      isChecked={selectedIds.has(row.member_id)}
                      onChange={() => toggleRow(row.member_id)}
                    />
                  </Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
                <Tr>
                  <Td colSpan={colSpan}>
                    <Text color="gray.500">{t('table.empty')}</Text>
                  </Td>
                </Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      {/* Read-only view modal (task 19.1) */}
      <Modal isOpen={isViewOpen} onClose={handleViewClose} isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{t('modal.title')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {detailLoading ? (
              <HStack><Spinner color="orange.300" /><Text>{t('modal.loading')}</Text></HStack>
            ) : selectedMember ? (
              <VStack spacing={2} align="stretch">
                <DetailRow label={t('modal.fields.memberId')} value={selectedMember.member_id} />
                <DetailRow label={t('modal.fields.name')} value={selectedMember.name} />
                <DetailRow label={t('modal.fields.email')} value={selectedMember.email} />
                <DetailRow label={t('modal.fields.status')} value={selectedMember.status} />
                <DetailRow
                  label={t('modal.fields.membershipType')}
                  value={selectedMember.membership_type as string | undefined}
                />
                <DetailRow
                  label={t('modal.fields.region')}
                  value={selectedMember.region as string | undefined}
                />
                {overlayFields.map(f => (
                  <DetailRow
                    key={f.key}
                    label={resolveLabel(f.label, lang, f.key)}
                    value={selectedMember[f.key] != null ? String(selectedMember[f.key]) : undefined}
                  />
                ))}
              </VStack>
            ) : null}
          </ModalBody>
          <ModalFooter>
            {/* Destructive action: delete (task 19.3) — red/ghost, left of the
                primary actions; opens a confirm step (never a one-click delete). */}
            <Button
              variant="ghost"
              colorScheme="red"
              mr="auto"
              onClick={handleDeleteOpen}
              isDisabled={!selectedMember}
            >
              {t('actions.delete')}
            </Button>
            {/* Single transition (task 20.3, R8.5) — ghost, opens the transition
                modal whose targets come FROM THE MODULE (not hardcoded). */}
            <Button
              variant="ghost"
              colorScheme="orange"
              mr={3}
              onClick={handleTransitionOpen}
              isDisabled={!selectedMember}
            >
              {t('actions.transition')}
            </Button>
            {/* Edit (task 19.2) — orange, opens the pre-filled edit modal. */}
            <Button
              colorScheme="orange"
              mr={3}
              onClick={handleEditOpen}
              isDisabled={!selectedMember}
            >
              {t('actions.edit')}
            </Button>
            <Button variant="ghost" onClick={handleViewClose}>{t('modal.close')}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Add / application modal (task 20.1, R8.3) */}
      <MembersAddModal
        isOpen={isAddOpen}
        onClose={onAddClose}
        fieldConfig={fieldConfig}
        onSaved={loadMembers}
      />

      {/* Edit modal (task 19.2, R8.2/R7.7) — pre-filled from the selected member. */}
      <MembersEditModal
        isOpen={isEditOpen}
        onClose={handleEditClose}
        member={selectedMember}
        fieldConfig={fieldConfig}
        onSaved={loadMembers}
      />

      {/* Delete confirm (task 19.3, R8.2) — names the member before deleting. */}
      <MembersDeleteConfirm
        isOpen={isDeleteOpen}
        onClose={handleDeleteClose}
        member={selectedMember}
        onDeleted={loadMembers}
      />

      {/* Single transition modal (task 20.3, R8.5) — target states FROM THE
          MODULE (field-config `lifecycle`), never hardcoded. */}
      <MembersTransitionModal
        isOpen={isTransitionOpen}
        onClose={handleTransitionClose}
        member={selectedMember}
        fieldConfig={fieldConfig}
        onDone={loadMembers}
      />

      {/* Bulk transition modal (task 20.4, R8.6) — over the checkbox selection. */}
      <MembersBulkTransitionModal
        isOpen={isBulkOpen}
        onClose={onBulkClose}
        memberIds={selectedIdList}
        fieldConfig={fieldConfig}
        onDone={handleBulkDone}
      />
    </Box>
  );
};

/** A single read-only label/value row inside the view modal. */
const DetailRow: React.FC<{ label: string; value?: string }> = ({ label, value }) => (
  <Flex justify="space-between" gap={4}>
    <Text color="gray.400" fontSize="sm">{label}</Text>
    <Text fontSize="sm">{value || '-'}</Text>
  </Flex>
);

export default MembersPage;
