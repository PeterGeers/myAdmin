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
  Table, Thead, Tbody, Tr, Th, Td, HStack, ButtonGroup, Badge, Checkbox, Select, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, RepeatIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useAuth } from '../context/AuthContext';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import {
  listMembers, getMember, getFieldConfig, exportMembers, listMembershipTypes,
} from '../services/membersApiService';
import { MembersAddModal } from '../components/members/MembersAddModal';
import { MembersEditModal } from '../components/members/MembersEditModal';
import { MembersDeleteConfirm } from '../components/members/MembersDeleteConfirm';
import { MembersViewBody } from '../components/members/MembersViewBody';
import { MembersTransitionModal } from '../components/members/MembersTransitionModal';
import { MembersBulkTransitionModal } from '../components/members/MembersBulkTransitionModal';
import { generateCsv, downloadCsv } from '../utils/csvExport';
import { renderFieldValue, isColumnCandidate } from '../components/members/fieldValue';
import type {
  Member, MemberRow, FieldConfig, FieldConfigField, LocalizedLabel, ViewContext, ScopeDimension,
  MembershipType,
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

/** The stable key of the synthesized default (empty-columns = all visible fields) context. */
const DEFAULT_CONTEXT_KEY = '__default__';

/**
 * Normalize the field-config `view_contexts` (design C-VIEW) to a NON-EMPTY list:
 * the module already returns exactly one default context (key `__default__`,
 * empty `columns`) when a tenant authored none, but we synthesize the same
 * sentinel defensively so the page always has ≥1 context to render.
 */
function normalizeViewContexts(cfg: FieldConfig | null): ViewContext[] {
  const authored = cfg?.view_contexts ?? [];
  if (authored.length > 0) return authored;
  return [{ key: DEFAULT_CONTEXT_KEY, columns: [] }];
}

/**
 * A context is selectable when it has no `permission_roles` (available to all)
 * or the caller holds any of them. `hasAnyRole` is passed in so the pure logic
 * stays testable and the hook is only called once at the component root.
 */
function isContextAvailable(
  ctx: ViewContext,
  hasAnyRole: (roles: string[]) => boolean,
): boolean {
  const roles = ctx.permission_roles ?? [];
  if (roles.length === 0) return true;
  return hasAnyRole(roles);
}

const MembersPage: React.FC = () => {
  const { t, i18n } = useTypedTranslation('members');
  const toast = useToast();
  const { hasAnyRole } = useAuth();
  const lang = (i18n?.language || 'nl').slice(0, 2);

  const [members, setMembers] = useState<Member[]>([]);
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  // The tenant's ACTIVE Lidmaatschap Beheer catalog entries (R5.8), fetched via
  // listMembershipTypes(true). Feed the add/edit modals' membership_type dropdown with
  // active-only types; the domain re-validates the chosen type authoritatively.
  const [membershipTypes, setMembershipTypes] = useState<MembershipType[] | null>(null);
  const [loading, setLoading] = useState(true);

  // Compact/full view switch (driven by field config: fixed ⊕ overlay columns).
  const [viewMode, setViewMode] = useState<'compact' | 'full'>('compact');

  // Selected view context (design C-VIEW). Defaults to the first AVAILABLE
  // context once the field config resolves (see the effect below).
  const [selectedContextKey, setSelectedContextKey] = useState<string>(DEFAULT_CONTEXT_KEY);

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

  // Load the ACTIVE membership-type catalog (R5.8) once — GET /membership-types?active_only=true.
  // The add/edit modals render the membership_type dropdown from these active-only entries; a
  // failed load leaves it null (the modals then fall back to the field-config embedded options).
  useEffect(() => {
    Promise.resolve(listMembershipTypes<MembershipType[]>(true))
      .then(types => setMembershipTypes(Array.isArray(types) ? types : []))
      .catch(() => setMembershipTypes(null));
  }, []);

  // Overlay (full-view-only) columns from the resolved field config: any field
  // that is not one of the fixed compact keys and is not the region dimension.
  // This is where PARAMETER-DRIVEN (overlay, origin `variable`) AND CALCULATED
  // (origin `calculated`, read-only — R5.2) fields become first-class column
  // candidates in the full/default view: the page renders whatever the field
  // config lists, uniformly. Field-level `visible === false` removes a field
  // from the candidate set (R5.1) — a hidden field is never a column.
  const overlayFields: FieldConfigField[] = useMemo(() => {
    const fixed = new Set<string>([...COMPACT_FIELD_KEYS, 'region', 'member_id']);
    const fields = fieldConfig?.fields ?? [];
    return fields
      .filter(f => !fixed.has(f.key) && isColumnCandidate(f))
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [fieldConfig]);

  // ── Scope / region pre-filter (task 4.2, design C-SCOPE; R5.3, R5.4) ──────────
  // The scope column (`region`) is surfaced two ways:
  //   1. a read-only purple Badge in the row (the SCOPE INDICATOR — already
  //      rendered below), and
  //   2. an ENUM-select PRE-FILTER whose options are the tenant's authored
  //      `config#scope` dimension `values` (parameter data, generic placeholder
  //      names by default — R4.5), drawn from `FieldConfig.dimensions`.
  // Row scope itself is ALWAYS enforced SERVER-SIDE (the module edge's
  // `resolve_scope_access` returns only in-scope rows from `GET /members`); this
  // is purely a client-side narrowing of the already-scoped rows and NEVER
  // invents scope. The filter is wired through the shared `useFilterableTable`
  // on the `region` key, so it applies IN EVERY view context (a context chooses
  // columns, never rows).
  const scopeDimension = useMemo<ScopeDimension | undefined>(() => {
    const dims = fieldConfig?.dimensions ?? [];
    // Prefer the `region` dimension (h-dcn's one wired dimension); otherwise the
    // first enabled dimension the tenant authored.
    return (
      dims.find(d => d.key === 'region')
      ?? dims.find(d => d.enabled !== false)
    );
  }, [fieldConfig]);

  // The enum options for the scope pre-filter, straight from the dimension's
  // authored `values`. Absent/empty → no options → the header falls back to the
  // free-text filter (the toolkit's default), never crashing.
  const scopeFilterOptions = useMemo<string[]>(
    () => scopeDimension?.values ?? [],
    [scopeDimension],
  );

  // ── View contexts (design C-VIEW) ────────────────────────────────────────────
  // The full list of authored contexts (or a single synthesized default when the
  // tenant authored none / the module returned nothing).
  const viewContexts: ViewContext[] = useMemo(
    () => normalizeViewContexts(fieldConfig),
    [fieldConfig],
  );

  // The contexts the current user may select: a context with empty/absent
  // `permission_roles` is available to everyone; otherwise it needs `hasAnyRole`.
  // We always keep at least ONE context available (fall back to the first context
  // — the default — so the dropdown is never empty and the page always renders).
  const availableContexts: ViewContext[] = useMemo(() => {
    const allowed = viewContexts.filter(ctx => isContextAvailable(ctx, hasAnyRole));
    return allowed.length > 0 ? allowed : [viewContexts[0]];
  }, [viewContexts, hasAnyRole]);

  // Keep the selection valid: default to (and snap back to) the first available
  // context whenever the resolved set changes or the current pick is no longer
  // permitted (e.g. after the field config / roles resolve).
  useEffect(() => {
    if (availableContexts.length === 0) return;
    const stillAvailable = availableContexts.some(c => c.key === selectedContextKey);
    if (!stillAvailable) {
      setSelectedContextKey(availableContexts[0].key);
    }
  }, [availableContexts, selectedContextKey]);

  // The context currently in effect (always resolves to an available context).
  const selectedContext: ViewContext = useMemo(
    () =>
      availableContexts.find(c => c.key === selectedContextKey)
      ?? availableContexts[0]
      ?? { key: DEFAULT_CONTEXT_KEY, columns: [] },
    [availableContexts, selectedContextKey],
  );

  // Does the selected context specify an explicit column set? Empty/absent
  // `columns` is the "all visible fields" sentinel → keep today's compact/full
  // derivation. A non-empty set drives a parameter-driven column list instead.
  const hasExplicitColumns = (selectedContext.columns?.length ?? 0) > 0;

  // Resolve the selected context's `columns` (field_keys) to actual field
  // descriptors, PRESERVING context order and SKIPPING any key not present in
  // `fieldConfig.fields` (Property 7 / R5.1a — never crash, just omit). A field
  // resolves the SAME whether it is fixed, parameter-driven (overlay), or
  // calculated (read-only) — they all live in `fieldConfig.fields` uniformly
  // (R5.1, R5.2). Field-level `visible === false` additionally drops the field
  // as a candidate (R5.1) — a context may name it, but a hidden field is skipped.
  const contextColumns: FieldConfigField[] = useMemo(() => {
    if (!hasExplicitColumns) return [];
    const byKey = new Map<string, FieldConfigField>(
      (fieldConfig?.fields ?? []).map(f => [f.key, f]),
    );
    return (selectedContext.columns ?? [])
      .map(key => byKey.get(key))
      .filter((f): f is FieldConfigField => f !== undefined && isColumnCandidate(f));
  }, [hasExplicitColumns, selectedContext, fieldConfig]);

  // Filterable-column gate: when the context lists `filterable_columns`, only
  // those keys render a FilterableHeader filter input; an empty/absent list keeps
  // today's filterable behavior (all headers that already carry filters).
  const filterableSet: Set<string> | null = useMemo(() => {
    const fc = selectedContext.filterable_columns;
    return fc && fc.length > 0 ? new Set(fc) : null;
  }, [selectedContext]);

  const isFilterable = useCallback(
    (key: string): boolean => (filterableSet ? filterableSet.has(key) : true),
    [filterableSet],
  );

  // Build flat rows; promote the region display value for the badge column.
  const memberRows: MemberRow[] = useMemo(
    () => members.map(m => ({
      ...m,
      region_display: (m.region as string) || '',
    })),
    [members],
  );

  // Feed the selected context's `default_sort` to the EXISTING toolkit; fall
  // back to today's default (name asc) when the context specifies none. The
  // context's `{field, direction}` shape matches `useFilterableTable`'s
  // `defaultSort` (direction is a `SortDirection`).
  const contextDefaultSort = selectedContext.default_sort;
  const defaultSort = useMemo(
    () =>
      contextDefaultSort
        ? { field: contextDefaultSort.field, direction: contextDefaultSort.direction }
        : { field: 'name', direction: 'asc' as const },
    [contextDefaultSort],
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
    defaultSort,
  });

  // Apply the selected context's `page_size` (design C-VIEW) as a simple client
  // slice over the already filtered+sorted rows. The page currently shows all
  // rows (no pager control yet); a positive `page_size` caps the first page in
  // the least-invasive way. Null/absent/≤0 keeps today's show-all behavior.
  const pageSize = selectedContext.page_size ?? null;
  const visibleData: MemberRow[] = useMemo(
    () => (pageSize && pageSize > 0 ? processedData.slice(0, pageSize) : processedData),
    [processedData, pageSize],
  );

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

  // ── Live statistics strip (task 4.3, design C-SURFACE; R5.4) ──────────────────
  // A live stats strip reusing the shared Chakra `Stat` card pattern
  // (`bg="gray.800"`, per steering 32; same shape as ZZPDebtors / PDFValidation).
  // Every figure is computed from `processedData` — the rows AFTER the shared
  // toolkit's filters + sort — so the strip recomputes automatically as the user
  // types a column filter, changes the scope enum-select, sorts, or SWITCHES VIEW
  // CONTEXT (the context feeds per-context defaults into the same toolkit, so the
  // strip follows the selection). `total` is the full scoped set the module
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

  // ── Row selection for bulk actions (task 20.4, R8.6) ─────────────────────────
  // The select-all header toggles every VISIBLE (`processedData`) row so the
  // selection tracks the shared filter/sort framework's current view.
  const visibleIds = useMemo(
    () => visibleData.map(r => r.member_id),
    [visibleData],
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

  // Export via the AUTHORITATIVE `export_members` module action (R5.6). We do
  // NOT build the CSV from the client-side `processedData`: instead we call
  // `exportMembers()` (GET /members/export), whose rows are scope-narrowed
  // SERVER-side by the module (R8.7 — the SPA never invents scope). The action
  // returns the same flat record shape as the list, so we serialize its rows to
  // CSV with the shared `csvExport.ts` helper (RFC-4180 escaping + BOM, the same
  // one ZZP/pivot use), using the resolved field set (fixed + overlay) for
  // columns. Empty result → info toast, no download; any failure → error toast.
  const handleExport = useCallback(async () => {
    try {
      const exportRows = await exportMembers<MemberRow[]>();

      if (exportRows.length === 0) {
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
      const rows = exportRows.map(row => columns.map(c => (row as Record<string, unknown>)[c.key]));
      const csv = generateCsv(headers, rows);

      const stamp = new Date().toISOString().slice(0, 10);
      downloadCsv(csv, `leden-${stamp}.csv`);
    } catch {
      toast({ title: t('export.error'), status: 'error' });
    }
  }, [overlayFields, lang, t, toast]);

  // Total column count (fixed compact + region + overlay when in full view + the
  // trailing selection column).
  const overlayColumns = viewMode === 'full' ? overlayFields : [];
  // For the default (all-visible-fields) context the header set is the fixed
  // compact columns + region + full-view overlay; for an explicit-columns
  // context it is exactly the resolved `contextColumns`. Either way a trailing
  // selection column is appended.
  const defaultColumnCount = COMPACT_FIELD_KEYS.length + 1 + overlayColumns.length;
  const colSpan = (hasExplicitColumns ? contextColumns.length : defaultColumnCount) + 1;

  // Only the default (all-visible-fields) context uses the compact/full switch;
  // an explicit-columns context defines its own column set, so the switch is
  // hidden for it. The context dropdown is shown whenever ≥2 contexts are
  // selectable (a single/default-only context needs no picker).
  const showViewSwitch = !hasExplicitColumns;
  const showContextDropdown = availableContexts.length > 1;

  return (
    <Box p={6}>
      {/* Header: title + view switch + primary actions (orange) */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('overview.title')}</Text>
        <HStack spacing={3}>
          {/* View-context dropdown (design C-VIEW) — lists only the contexts the
              user's roles permit; selecting one re-renders its column set via
              the shared toolkit. Shown only when ≥2 contexts are selectable. */}
          {showContextDropdown && (
            <Select
              size="sm"
              w="auto"
              color="white"
              bg="gray.700"
              aria-label={t('viewContext.label')}
              value={selectedContextKey}
              onChange={(e) => setSelectedContextKey(e.target.value)}
            >
              {availableContexts.map(ctx => (
                <option key={ctx.key} value={ctx.key}>
                  {resolveLabel(ctx.label, lang, ctx.key)}
                </option>
              ))}
            </Select>
          )}
          {/* Compact/full view switch (default/all-visible-fields context only) */}
          {showViewSwitch && (
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
          )}
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
            onClick={() => { void handleExport(); }}
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

      {/* Live statistics strip (task 4.3, design C-SURFACE; R5.4) — reuses the
          shared stats-strip convention (steering 32; `bg="gray.800"` cards, same
          shape as MediaAssetAdmin's `StatCard`). Built from plain `Box`/`Text`
          rather than Chakra's `Stat`/`StatLabel`/`StatNumber`: the `Stat*` family
          resolves to `undefined` under the test runner's ESM interop (it would
          crash the whole page with "Element type is invalid"), whereas
          `Box`/`Text` render identically in-app and under test. Every figure is
          recomputed from `processedData` (the filtered+sorted rows), so the strip
          follows every column filter, sort, scope-select, and view-context switch. */}
      {!loading && (
        <Flex
          mb={4}
          gap={4}
          wrap="wrap"
          data-testid="members-stats-strip"
        >
          <StatCard
            label={t('stats.total')}
            value={stats.total}
            valueColor="white"
            testId="stat-total"
          />
          <StatCard
            label={t('stats.filtered')}
            value={stats.filtered}
            valueColor="orange.300"
            testId="stat-filtered"
          />
          <StatCard
            label={t('stats.active')}
            value={stats.active}
            valueColor="green.400"
            testId="stat-active"
          />
          <StatCard
            label={t('stats.regions')}
            value={stats.regions}
            valueColor="purple.300"
            testId="stat-regions"
          />
        </Flex>
      )}

      {loading ? (
        <HStack color="white"><Spinner color="orange.300" /><Text>{t('table.loading')}</Text></HStack>
      ) : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                {hasExplicitColumns ? (
                  // Explicit-columns context (design C-VIEW): render exactly the
                  // resolved `contextColumns` in context order. `filterable_columns`
                  // gates which headers carry a filter input.
                  contextColumns.map(f => (
                    <FilterableHeader
                      key={f.key}
                      label={resolveLabel(f.label, lang, f.key)}
                      filterValue={isFilterable(f.key) ? (filters[f.key] ?? '') : undefined}
                      onFilterChange={
                        isFilterable(f.key) ? (v) => setFilter(f.key, v) : undefined
                      }
                      placeholder={t('filters.placeholder')}
                      // The scope column gets the enum pre-filter (config#scope
                      // dimension values); every other column keeps the free-text
                      // filter. Applies regardless of the selected context.
                      filterOptions={
                        f.key === 'region' && scopeFilterOptions.length > 0
                          ? scopeFilterOptions
                          : undefined
                      }
                      sortable
                      sortDirection={columnSortDirection(f.key)}
                      onSort={() => handleSort(f.key)}
                    />
                  ))
                ) : (
                  <>
                    <FilterableHeader
                      label={t('columns.name')}
                      filterValue={isFilterable('name') ? filters.name : undefined}
                      onFilterChange={isFilterable('name') ? (v) => setFilter('name', v) : undefined}
                      placeholder={t('filters.placeholder')}
                      sortable
                      sortDirection={columnSortDirection('name')}
                      onSort={() => handleSort('name')}
                    />
                    <FilterableHeader
                      label={t('columns.email')}
                      filterValue={isFilterable('email') ? filters.email : undefined}
                      onFilterChange={isFilterable('email') ? (v) => setFilter('email', v) : undefined}
                      placeholder={t('filters.placeholder')}
                      sortable
                      sortDirection={columnSortDirection('email')}
                      onSort={() => handleSort('email')}
                    />
                    <FilterableHeader
                      label={t('filters.status')}
                      filterValue={isFilterable('status') ? filters.status : undefined}
                      onFilterChange={isFilterable('status') ? (v) => setFilter('status', v) : undefined}
                      placeholder={t('filters.placeholder')}
                      sortable
                      sortDirection={columnSortDirection('status')}
                      onSort={() => handleSort('status')}
                    />
                    <FilterableHeader
                      label={t('filters.type')}
                      filterValue={isFilterable('membership_type') ? filters.membership_type : undefined}
                      onFilterChange={
                        isFilterable('membership_type') ? (v) => setFilter('membership_type', v) : undefined
                      }
                      placeholder={t('filters.placeholder')}
                      sortable
                      sortDirection={columnSortDirection('membership_type')}
                      onSort={() => handleSort('membership_type')}
                    />
                    <FilterableHeader
                      label={t('filters.region')}
                      filterValue={isFilterable('region') ? filters.region : undefined}
                      onFilterChange={isFilterable('region') ? (v) => setFilter('region', v) : undefined}
                      placeholder={t('filters.placeholder')}
                      // Scope pre-filter: an enum-select drawn from the tenant's
                      // config#scope dimension values (R5.4). Falls back to the
                      // free-text filter when the tenant authored no values.
                      filterOptions={
                        scopeFilterOptions.length > 0 ? scopeFilterOptions : undefined
                      }
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
                  </>
                )}
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
              {visibleData.map(row => (
                <Tr
                  key={row.member_id}
                  _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(row)}
                >
                  {hasExplicitColumns ? (
                    // Explicit-columns context: one cell per resolved column.
                    // `region` keeps the read-only Badge treatment; everything
                    // else renders its stringified value.
                    contextColumns.map(f => (
                      <Td key={f.key}>
                        {f.key === 'region'
                          ? (row.region_display
                            ? <Badge colorScheme="purple">{row.region_display}</Badge>
                            : <Text color="gray.500">-</Text>)
                          : renderFieldValue(f, row[f.key], lang)}
                      </Td>
                    ))
                  ) : (
                    <>
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
                        <Td key={f.key}>{renderFieldValue(f, row[f.key], lang)}</Td>
                      ))}
                    </>
                  )}
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
              // Sectioned read-only view over the RESOLVED field set (s5c task 4.4): grouped by
              // functional_group, honoring visibility + show_when. Always show the member id row.
              <VStack spacing={4} align="stretch">
                <Flex justify="space-between" gap={4}>
                  <Text color="gray.400" fontSize="sm">{t('modal.fields.memberId')}</Text>
                  <Text fontSize="sm">{selectedMember.member_id || '-'}</Text>
                </Flex>
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

/**
 * One card in the live statistics strip (task 4.3). Deliberately built from
 * `Box`/`Text` (not Chakra `Stat`/`StatLabel`/`StatNumber`, which are `undefined`
 * under the test runner's ESM interop) while keeping the same visual shape as the
 * shared stats-strip pattern: a `gray.800` card with a muted label over a large
 * colored number. `testId` is placed on the number node so tests read the figure.
 */
const StatCard: React.FC<{
  label: string;
  value: number;
  valueColor: string;
  testId: string;
}> = ({ label, value, valueColor, testId }) => (
  <Box bg="gray.800" borderRadius="md" p={4} minW="140px" flex="1">
    <Text color="gray.400" fontSize="sm">{label}</Text>
    <Text color={valueColor} fontSize="2xl" fontWeight="bold" data-testid={testId}>
      {value}
    </Text>
  </Box>
);

export default MembersPage;
