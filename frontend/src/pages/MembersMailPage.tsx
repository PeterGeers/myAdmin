/**
 * Members Mail page (tenant administrator > members > mail — the
 * `Members_Mail_Area`). Hosts the RELOCATED applications inbox
 * (members-overview-tweaks Req 6.2–6.4): the inbox was removed from
 * `MembersPage` in task 8.1 and now lives here as its own tenant-admin route.
 *
 * COMPOSES the same machinery `MembersPage` used — it does NOT rebuild the grid
 * (design "Relocate the applications inbox"):
 * - the config/prefs hook (`useMembersData`), the DynamoDB cursor pager
 *   (`useMembersCursorPaging`), the unified column model (`useMembersColumns`),
 *   the Table Filter Framework v2 (`useFilterableTable`) and the presentational
 *   `MembersTable` — identical wiring to the overview grid;
 * - the applications-inbox preset bar (`MembersInboxBar`) + its self-contained
 *   wiring hook (`useApplicationsInbox`), reused VERBATIM.
 *
 * The inbox drives this one member grid through the framework's `setFilter`:
 * - Pinned to `status = application` (Req 6.3): the page activates the inbox on
 *   mount so the grid opens on the applications view, and the "Applications"
 *   preset re-pins it.
 * - Retains the `DUP` / `NO_NOTIFY` keyword quick-filters over
 *   `overlay.additional_info` (Req 6.4): the preset bar's keyword buttons set
 *   the `additional_info` column filter to the stable SAM keyword while keeping
 *   the `status = application` pin.
 *
 * Guarded for the tenant administrator role at the route (see `AppRoutes.tsx`
 * `members-mail` case → `ProtectedRoute requiredRoles={['Tenant_Admin']}`), like
 * the other tenant-admin routes.
 *
 * _Requirements: 6.2, 6.3, 6.4_
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import {
  Box, HStack, Text, Spinner, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalCloseButton,
  ModalFooter, Button, VStack,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { getMember } from '../services/membersApiService';
import { MembersViewBody } from '../components/members/MembersViewBody';
import { useMembersData } from '../components/members/overview/useMembersData';
import { useMembersColumns } from '../components/members/overview/useMembersColumns';
import { useMembersCursorPaging } from '../components/members/overview/useMembersCursorPaging';
import { useMembersSelection } from '../components/members/overview/useMembersSelection';
import { MembersTable } from '../components/members/overview/MembersTable';
import { MembersPaginationBar } from '../components/members/overview/MembersPaginationBar';
import { MembersInboxBar } from '../components/members/overview/MembersInboxBar';
import { useApplicationsInbox } from '../components/members/overview/useApplicationsInbox';
import type { Member, MemberRow } from '../types/members';

const MembersMailPage: React.FC = () => {
  const { t, i18n } = useTypedTranslation('members');
  const lang = (i18n?.language || 'nl').slice(0, 2);

  // ── Config / membership types / column prefs (same hook as the overview) ─────
  const {
    fieldConfig,
    chosenKeys,
    handleColumnsChange,
  } = useMembersData(t);

  // ── Members list: DynamoDB cursor paging driven by the rows-per-page selector ─
  // Identical wiring to the overview grid — the inbox is a VIEW over this one
  // grid, not a new table.
  const {
    members,
    loading,
    pageSize,
    setPageSize,
    canNext,
    canPrev,
    goNext,
    goPrev,
  } = useMembersCursorPaging(t);

  // No global all-fields search on the mail area — the applications inbox is the
  // preset that drives this grid. Keep an empty query so the column model's
  // search stage is a no-op.
  const globalSearch = '';

  // Read-only view modal (same row-click behaviour as the overview grid).
  const { isOpen: isViewOpen, onOpen: onViewOpen, onClose: onViewClose } = useDisclosure();
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // ── Unified column model + row-derivation (search → flatten → columns) ───────
  const {
    columns,
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

  const visibleData = processedData;

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ── Applications-inbox preset wiring (reused VERBATIM, Req 6.2–6.4) ───────────
  // `useApplicationsInbox` composes the framework's `setFilter` + the column
  // model: `activateInbox` pins `status = application` and surfaces the
  // `additional_info` note column; `filterKeyword('DUP' | 'NO_NOTIFY')` narrows
  // the inbox to the keyword note while KEEPING the status pin; `clearInbox`
  // drops both filters.
  const { activateInbox, filterKeyword, clearInbox } = useApplicationsInbox({
    setFilter,
    chosenKeys,
    onColumnsChange: handleColumnsChange,
  });

  // Pin the grid to the applications view on mount (Req 6.3): this is the
  // Members_Mail_Area — it OPENS on the applications inbox rather than the full
  // overview. Run once, after the field config has resolved so the note column
  // can be surfaced; a ref guards against re-pinning on every render.
  const pinnedRef = useRef(false);
  useEffect(() => {
    if (pinnedRef.current || !fieldConfig) return;
    pinnedRef.current = true;
    activateInbox();
  }, [fieldConfig, activateInbox]);

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

  // Total column count = the unified column model + the trailing selection column.
  const colSpan = useMemo(() => columns.length + 1, [columns.length]);

  return (
    <Box p={6}>
      {/* Applications-inbox preset bar (Req 6.2): "Applications" re-pins the grid
          to status=application; "Possible duplicates" / "Not auto-notified"
          quick-filter it to the DUP / NO_NOTIFY keyword notes (Req 6.4);
          "Clear" drops the inbox filters. */}
      <MembersInboxBar
        t={t}
        onActivateInbox={activateInbox}
        onFilterKeyword={filterKeyword}
        onClear={clearInbox}
      />

      {/* Rows-per-page selector + cursor prev/next, above the table (same as the
          overview grid). */}
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

      {/* Read-only view modal — same composition as the overview grid. */}
      <Modal isOpen={isViewOpen} onClose={handleViewClose} isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>{t('modal.title')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {detailLoading ? (
              <HStack><Spinner color="orange.300" /><Text>{t('modal.loading')}</Text></HStack>
            ) : selectedMember ? (
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
            <Button variant="ghost" onClick={handleViewClose}>{t('modal.close')}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default MembersMailPage;
