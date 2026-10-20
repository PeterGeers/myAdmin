/**
 * Members Overview page (Leden Overzicht) — Chakra Table with shared filters,
 * sort, a compact/full view switch driven by the resolved field config, a
 * region column, and a row-click view modal.
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
 * (tasks 19–20).
 *
 * Export (task 20.2, R8.4): a header-right "Exporteren" action produces a CSV of
 * the scope-filtered rows using the shared `frontend/src/utils/csvExport.ts`
 * helper. The CSV inherently respects scope (R8.7) — never inventing scope
 * client-side.
 *
 * STRUCTURE (code-quality-fixes 2026-10-15, task 6): this page was 1161 lines; it
 * now COMPOSES cohesive overview pieces extracted under
 * `components/members/overview/` — the config/prefs hook (`useMembersData`), the
 * unified column model (`useMembersColumns`), the rows-per-page selector + cursor
 * pager (`useMembersCursorPaging`, Req 25), the bulk-selection hook
 * (`useMembersSelection`), and
 * the presentational `MembersToolbar` / `MembersStatsStrip` / `MembersTable` /
 * `MembersPaginationBar`. Behaviour is identical; the default export + import
 * surface are unchanged so routing/consumers are unaffected.
 *
 * Reference: `frontend/src/pages/ZZPInvoices.tsx`, `.kiro/steering/32-frontend-ui.md`.
 *
 * _Requirements: R7.5, R7.6, R7.9, R8.4, R8.7_
 */

import React, { useState, useCallback, useMemo } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, HStack, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useAuth } from '../context/AuthContext';
import { useFilterableTable } from '../hooks/useFilterableTable';
import {
  getMember, exportMembers,
} from '../services/membersApiService';
import ColumnChooser from '../components/members/ColumnChooser';
import { MembersAddModal } from '../components/members/MembersAddModal';
import { MembersEditModal } from '../components/members/MembersEditModal';
import { MembersDeleteConfirm } from '../components/members/MembersDeleteConfirm';
import { MembersViewBody } from '../components/members/MembersViewBody';
import { generateCsv, downloadCsv } from '../utils/csvExport';
import { renderFieldValue, valueFor } from '../components/members/fieldValue';
import { formFields, groupFieldsBySection } from '../components/members/fieldForm';
import { resolveLabel } from '../components/members/overview/membersOverviewModel';
import { useMembersData } from '../components/members/overview/useMembersData';
import { useMembersColumns } from '../components/members/overview/useMembersColumns';
import { useMembersCursorPaging } from '../components/members/overview/useMembersCursorPaging';
import { useMembersSelection } from '../components/members/overview/useMembersSelection';
import { MembersToolbar } from '../components/members/overview/MembersToolbar';
import { MembersInboxBar } from '../components/members/overview/MembersInboxBar';
import { useApplicationsInbox } from '../components/members/overview/useApplicationsInbox';
import { MembersStatsStrip } from '../components/members/overview/MembersStatsStrip';
import { MembersTable } from '../components/members/overview/MembersTable';
import { MembersPaginationBar } from '../components/members/overview/MembersPaginationBar';
import type { Member, MemberRow, FieldConfigField } from '../types/members';

const MembersPage: React.FC = () => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const { hasAnyRole } = useAuth();
  const lang = (i18n?.language || 'nl').slice(0, 2);

  // ── Config / membership types / column prefs (no longer the members list) ────
  const {
    fieldConfig,
    membershipTypes,
    chosenKeys,
    handleColumnsChange,
  } = useMembersData(t);

  // ── Members list: DynamoDB cursor paging driven by the rows-per-page selector ─
  // (spec 02, Task 1.17 / Req 25). `members` is ONE server page; prev/next walk
  // the opaque LastEvaluatedKey cursor the read path returns. The filter/sort/
  // search toolkit below narrows WITHIN the current server page. `reload()`
  // re-fetches from the first page after a create/edit/delete.
  const {
    members,
    loading,
    pageSize,
    setPageSize,
    canNext,
    canPrev,
    goNext,
    goPrev,
    reload: loadMembers,
  } = useMembersCursorPaging(t);

  // Global all-fields search (member-field-search Option 1). A single free-text
  // query matched against EVERY candidate field of each row — including nested
  // overlay / calculated fields the overview does not surface as columns — so a
  // user can find a value in a non-visible field without knowing which column it
  // lives in. Narrows the rows BEFORE the per-column filter/sort toolkit, so
  // stats, column filters, sort, selection and export all follow automatically.
  const [globalSearch, setGlobalSearch] = useState('');

  // Read-only view modal (task 19.1).
  const { isOpen: isViewOpen, onOpen: onViewOpen, onClose: onViewClose } = useDisclosure();
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Add / application modal (task 20.1).
  const { isOpen: isAddOpen, onOpen: onAddOpen, onClose: onAddClose } = useDisclosure();

  // Edit modal (task 19.2) + delete confirm (task 19.3).
  const { isOpen: isEditOpen, onOpen: onEditOpen, onClose: onEditClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();

  // Column chooser modal (session-columns task 4.1, design C2/C8).
  const {
    isOpen: isColumnChooserOpen, onOpen: onColumnChooserOpen, onClose: onColumnChooserClose,
  } = useDisclosure();

  // ── Unified column model + row-derivation (search → flatten → columns) ───────
  const {
    memberRows,
    columns,
    effectiveChosenKeys,
    columnLabel,
    renderCell,
    isFilterable,
    enrichedRows,
    dynamicInitialFilters,
    defaultSort,
  } = useMembersColumns({ members, fieldConfig, chosenKeys, globalSearch, lang, t });

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<MemberRow>(enrichedRows, {
    initialFilters: dynamicInitialFilters,
    defaultSort,
  });

  // ── Applications inbox preset (task 7.2, R8b.4/R8b.5/F3) ─────────────────────
  // The staff applications inbox is the EXISTING member grid pinned to
  // `status = application` via the Table Filter Framework v2 (`setFilter`), with
  // the `DUP` / `NO_NOTIFY` keyword notes on `overlay.additional_info`
  // keyword-filterable in that same grid. No new grid — a preset over the one
  // overview the framework already drives.
  const { activateInbox, filterKeyword, clearInbox } = useApplicationsInbox({
    setFilter,
    // Pass the EFFECTIVE chosen keys (the user's saved set, or the first-time
    // compact default) so surfacing the note column PRESERVES the visible columns
    // instead of collapsing a first-time user's default view to just the note.
    chosenKeys: effectiveChosenKeys,
    onColumnsChange: handleColumnsChange,
  });

  // ── Visible rows = the filtered/sorted CURRENT server page (Req 25) ──────────
  // With DynamoDB cursor paging the page already holds exactly one server page;
  // the shared toolkit's filter/sort/search narrows WITHIN that page. There is no
  // client-side slice — prev/next walk the server cursor (no SQL-style offset).
  const visibleData = processedData;

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ── Live statistics strip (task 4.3, design C-SURFACE; R5.4) ──────────────────
  // Every figure is computed from `processedData` (the rows AFTER the shared
  // toolkit's filters + sort), so the strip recomputes automatically as the user
  // types a column filter or sorts. `total` is the full scoped set the module
  // returned; `filtered` is the currently-visible subset.
  const stats = useMemo(() => {
    const total = memberRows.length;
    const filtered = processedData.length;
    const active = processedData.filter(
      r => String(r.status ?? '').toLowerCase() === 'active',
    ).length;
    const regions = new Set(
      processedData
        .map(r => (r.region_display ?? '').trim())
        .filter(v => v.length > 0),
    ).size;
    return { total, filtered, active, regions };
  }, [memberRows, processedData]);

  // ── Row selection (checkbox column) ──────────────────────────────────────────
  const {
    selectedIds,
    allVisibleSelected,
    someVisibleSelected,
    toggleSelectAll,
    toggleRow,
  } = useMembersSelection(visibleData);

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

  // Delete (task 19.3): open the confirm dialog for the selected member.
  const handleDeleteOpen = () => {
    onViewClose();
    onDeleteOpen();
  };

  const handleDeleteClose = () => {
    onDeleteClose();
    setSelectedMember(null);
  };

  // Export via the AUTHORITATIVE `export_members` module action (R5.6). We do
  // NOT build the CSV from the client-side `processedData`: instead we call
  // `exportMembers()` (GET /members/export), whose rows are scope-narrowed
  // SERVER-side by the module (R8.7). The action returns the same flat record
  // shape as the list, so we serialize its rows to CSV with the shared
  // `csvExport.ts` helper, using the resolved field set (fixed + overlay) for
  // columns. Empty result → info toast, no download; any failure → error toast.
  const handleExport = useCallback(async () => {
    try {
      const exportRows = await exportMembers<MemberRow[]>();

      if (exportRows.length === 0) {
        toast({ title: t('export.empty'), status: 'info' });
        return;
      }

      // Columns are driven by the SAME resolved field config the view modal uses (R4.9): the
      // full visible field set (fixed base ⊕ overlay ⊕ calculated), sectioned by
      // functional_group in the same order, flattened into a single column list. `formFields`
      // already omits the internal `member_id` UUID + system timestamps (s5k R1), and each cell
      // resolves through the shared nested-shape accessor (`valueFor`) + presenter
      // (`renderFieldValue`). show_when is a per-member predicate; a CSV needs a uniform column
      // set, so we include every visible field as a column and let an absent value render as the
      // placeholder dash.
      const fields = formFields(fieldConfig);
      const sections = groupFieldsBySection(fields, fieldConfig?.functional_groups);
      const orderedFields: FieldConfigField[] = sections.flatMap(s => s.fields);

      const headers = orderedFields.map(f => resolveLabel(f.label, lang, f.key));
      const rows = exportRows.map(row =>
        orderedFields.map(f => renderFieldValue(f, valueFor(row, f.group, f.key), lang)),
      );
      const csv = generateCsv(headers, rows);

      const stamp = new Date().toISOString().slice(0, 10);
      downloadCsv(csv, `leden-${stamp}.csv`);
    } catch {
      toast({ title: t('export.error'), status: 'error' });
    }
  }, [fieldConfig, lang, t, toast]);

  // Total column count = the unified column model (member_number ⊕ chosen) + the
  // trailing selection column.
  const colSpan = columns.length + 1;

  return (
    <Box p={6}>
      {/* Header: title + global search + primary actions (orange) */}
      <MembersToolbar
        t={t}
        loading={loading}
        globalSearch={globalSearch}
        setGlobalSearch={setGlobalSearch}
        onColumnChooserOpen={onColumnChooserOpen}
        canExport={hasAnyRole(['Tenant_Admin', 'SysAdmin'])}
        onExport={() => { void handleExport(); }}
        onAddOpen={onAddOpen}
      />

      {/* Applications inbox preset (task 7.2, R8b.4/R8b.5/F3): pins the existing
          grid to status=application + exposes DUP/NO_NOTIFY keyword filters over
          overlay.additional_info — a view of the one overview, not a new grid. */}
      {!loading && (
        <MembersInboxBar
          t={t}
          onActivateInbox={activateInbox}
          onFilterKeyword={filterKeyword}
          onClear={clearInbox}
        />
      )}

      {/* Live statistics strip (task 4.3, design C-SURFACE; R5.4). */}
      {!loading && <MembersStatsStrip stats={stats} t={t} />}

      <MembersTable
        loading={loading}
        columns={columns}
        visibleData={visibleData}
        colSpan={colSpan}
        columnLabel={columnLabel}
        renderCell={renderCell}
        isFilterable={isFilterable}
        filters={filters}
        setFilter={setFilter}
        columnSortDirection={columnSortDirection}
        handleSort={handleSort}
        allVisibleSelected={allVisibleSelected}
        someVisibleSelected={someVisibleSelected}
        toggleSelectAll={toggleSelectAll}
        selectedIds={selectedIds}
        toggleRow={toggleRow}
        onRowClick={handleRowClick}
        t={t}
      />

      {/* Rows-per-page selector (50/100/250/500/Max) + cursor prev/next (Req 25). */}
      <MembersPaginationBar
        loading={loading}
        pageSize={pageSize}
        onPageSizeChange={setPageSize}
        canNext={canNext}
        canPrev={canPrev}
        onNext={goNext}
        onPrev={goPrev}
        pageItemCount={visibleData.length}
        t={t}
      />

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
              // Sectioned read-only view over the RESOLVED field set (s5c task 4.4): grouped by
              // functional_group, honoring visibility + show_when. The internal member_id (UUID)
              // is NOT shown — the human-facing Lidnummer (member_number) already renders in the
              // Membership/Lidmaatschap group.
              <VStack spacing={4} align="stretch">
                <MembersViewBody
                  fieldConfig={fieldConfig}
                  member={selectedMember}
                  lang={lang}
                />
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
            {/* Edit (task 19.2) — orange, opens the pre-filled edit modal.
                Status is now an ordinary enum field edited here (no transition
                engine) — the member edit modal renders it from the resolved
                field config like any other field. */}
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
        membershipTypes={membershipTypes}
        onSaved={loadMembers}
      />

      {/* Edit modal (task 19.2, R8.2/R7.7) — pre-filled from the selected member. */}
      <MembersEditModal
        isOpen={isEditOpen}
        onClose={handleEditClose}
        member={selectedMember}
        fieldConfig={fieldConfig}
        membershipTypes={membershipTypes}
        onSaved={loadMembers}
      />

      {/* Delete confirm (task 19.3, R8.2) — names the member before deleting. */}
      <MembersDeleteConfirm
        isOpen={isDeleteOpen}
        onClose={handleDeleteClose}
        member={selectedMember}
        onDeleted={loadMembers}
      />

      {/* Column chooser modal (session-columns task 4.1, design C2/C8). Renders
          every candidate field via the shared FieldChecklist; the user's picks
          (minus the always-on member_number) drive `chosenKeys`. Each change is
          applied optimistically AND persisted (handleColumnsChange). */}
      <ColumnChooser
        isOpen={isColumnChooserOpen}
        onClose={onColumnChooserClose}
        fieldConfig={fieldConfig}
        // Flag the columns ACTUALLY shown: `effectiveChosenKeys` is the user's
        // saved list when they have one, else the first-time default/compact set.
        selectedKeys={effectiveChosenKeys}
        language={lang}
        onChange={handleColumnsChange}
      />
    </Box>
  );
};

export default MembersPage;
