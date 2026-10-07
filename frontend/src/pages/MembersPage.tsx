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
  Table, Thead, Tbody, Tr, Th, Td, HStack, ButtonGroup, Checkbox, Select, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, ModalFooter, VStack,
  Input, InputGroup, InputLeftElement, InputRightElement, IconButton,
} from '@chakra-ui/react';
import { AddIcon, DownloadIcon, RepeatIcon, SearchIcon, CloseIcon, SettingsIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useAuth } from '../context/AuthContext';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import {
  listMembers, getMember, getFieldConfig, exportMembers, listMembershipTypes,
  getColumnPreferences, saveColumnPreferences,
} from '../services/membersApiService';
import ColumnChooser, { ALWAYS_ON_COLUMN_KEY } from '../components/members/ColumnChooser';
import { MembersAddModal } from '../components/members/MembersAddModal';
import { MembersEditModal } from '../components/members/MembersEditModal';
import { MembersDeleteConfirm } from '../components/members/MembersDeleteConfirm';
import { MembersViewBody } from '../components/members/MembersViewBody';
import { MembersTransitionModal } from '../components/members/MembersTransitionModal';
import { MembersBulkTransitionModal } from '../components/members/MembersBulkTransitionModal';
import { generateCsv, downloadCsv } from '../utils/csvExport';
import { renderFieldValue, isColumnCandidate, valueFor } from '../components/members/fieldValue';
import { coerceByType, shouldFlatten } from '../components/members/columnValue';
import { formFields, groupFieldsBySection } from '../components/members/fieldForm';
import type {
  Member, MemberRow, FieldConfig, FieldConfigField, LocalizedLabel, ViewContext, ScopeDimension,
  MembershipType,
} from '../types/members';

/** The always-visible (compact) fixed columns, in display order. Lidnummer (member_number)
 *  leads — it is the member's human-facing identifier (M00000…), NOT the internal member_id UUID. */
const COMPACT_FIELD_KEYS = ['member_number', 'name', 'email', 'status', 'membership_type'] as const;

/** The leading, always-present fixed column (session-columns R7.1). Pinned first
 *  by the unified column model (design C3) and never removable. */
const MEMBER_NUMBER_KEY = 'member_number';

/**
 * Legacy per-column label i18n keys for the fixed compact columns + region
 * (session-columns C3). The pre-unification render paths labeled these specific
 * keys from the `members` namespace (`columns.*` / `filters.*`) rather than the
 * field-config label, and the existing suites assert on those exact labels (e.g.
 * `Filter by filters.region`, `Sort by columns.name`). The unified column model
 * preserves them: a fixed key resolves to its legacy i18n label, every other
 * column to its field-config `resolveLabel`.
 */
const FIXED_COLUMN_LABEL_KEYS: Record<string, string> = {
  member_number: 'columns.memberNumber',
  name: 'columns.name',
  email: 'columns.email',
  status: 'filters.status',
  membership_type: 'filters.type',
  region: 'filters.region',
};

/** Column filter keys — region/status/type plus the compact fixed fields. */
const INITIAL_FILTERS: Record<string, string> = {
  member_number: '',
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
 * One column in the unified column model (session-columns design C3). A thin
 * wrapper over a resolved `FieldConfigField` in render order — the single shape
 * the one header map + one cell map iterate, so fixed / context / session
 * columns all flow through identical FilterableHeader wiring (OQ-2).
 */
type OverviewColumn = { field: FieldConfigField };

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

  // Global all-fields search (member-field-search Option 1). A single free-text
  // query matched against EVERY candidate field of each row — including nested
  // overlay / calculated fields the overview does not surface as columns — so a
  // user can find a value in a non-visible field without knowing which column it
  // lives in. Narrows the rows BEFORE the per-column filter/sort toolkit, so
  // stats, column filters, sort, selection and export all follow automatically.
  // Scope-safe: it only ever narrows the already scope-authorized row set.
  const [globalSearch, setGlobalSearch] = useState('');

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

  // Column chooser modal (session-columns task 4.1, design C2/C8) — opened from a
  // toolbar button; lets the user pick which candidate fields show as columns.
  const {
    isOpen: isColumnChooserOpen, onOpen: onColumnChooserOpen, onClose: onColumnChooserClose,
  } = useDisclosure();

  // The user's own ordered chosen-column keys (session-columns R3.1). This is the
  // single source of which non-fixed columns show; member_number is implied +
  // pinned first by the model (R7), so it is never part of this list. Seeded on
  // mount from the persisted `getColumnPreferences()` once the field config
  // resolves (C8) — empty for a first-time user (R6.4). The unified column model
  // + flatten that CONSUME this list are tasks 4.2/4.3/4.4.
  const [chosenKeys, setChosenKeys] = useState<string[]>([]);

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

  // ── Seed the chosen-column list from the persisted preferences (C8 load) ──────
  // Once the field config resolves, fetch the user's saved column keys and seed
  // `chosenKeys`, resolving each key against the field config and SKIPPING any
  // that no longer resolves (dangling — field removed/hidden, R6.6) or is
  // `member_number` (implied + always-on, never stored, R7.3). An empty / unset
  // response leaves the list empty — the first-time default (R6.4; the admin
  // default overlay itself is applied by the unified column model in task 4.2).
  // A failed GET is non-fatal: the user simply starts from an empty chosen set.
  useEffect(() => {
    if (!fieldConfig) return;
    let cancelled = false;
    const resolvable = new Set(
      (fieldConfig.fields ?? [])
        .filter(f => !!f && typeof f.key === 'string' && f.key !== '')
        .map(f => f.key),
    );
    // `Promise.resolve(...)` wraps the call so a test auto-mock that returns a
    // bare value (not a promise) is tolerated — the same defensive pattern the
    // membership-type load above uses.
    Promise.resolve(getColumnPreferences())
      .then(prefs => {
        if (cancelled || !prefs) return;
        const seeded = (prefs.columns ?? []).filter(
          key => key !== ALWAYS_ON_COLUMN_KEY && resolvable.has(key),
        );
        setChosenKeys(seeded);
      })
      .catch(() => {
        // Non-fatal: keep the empty first-time default; the user can still choose.
      });
    return () => { cancelled = true; };
  }, [fieldConfig]);

  // ── Apply + persist a chooser change (C8 save) ───────────────────────────────
  // The chooser emits the FULL ordered chosen-key list (never member_number).
  // We update local state OPTIMISTICALLY so the view changes immediately, then
  // persist the full list via `saveColumnPreferences()` (full replace, R6.5). A
  // failed save shows a NON-BLOCKING toast and KEEPS the optimistic local change
  // — the user never loses their working column set (design C8 error handling).
  const handleColumnsChange = useCallback((nextKeys: string[]) => {
    setChosenKeys(nextKeys);
    // `Promise.resolve(...)` tolerates a non-promise mock return in tests while
    // keeping the real wrapper's rejection path (→ non-blocking toast) intact.
    Promise.resolve(saveColumnPreferences(nextKeys)).catch(() => {
      toast({ title: t('columnChooser.toast.saveError'), status: 'error' });
    });
  }, [toast, t]);

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
    const fixed = new Set<string>([...COMPACT_FIELD_KEYS, 'region', 'member_id', 'member_number']);
    const fields = fieldConfig?.fields ?? [];
    return fields
      .filter(f => !fixed.has(f.key) && isColumnCandidate(f))
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [fieldConfig]);

  // ── Scope / region dimension resolution (task 4.2, design C-SCOPE; R5.3) ──────
  // The scope column (`region`) is surfaced as a plain field value in the row
  // (standard column layout, no badge) and filtered/sorted through the standard
  // Table Filter Framework free-text input, exactly like every other column.
  // Row scope itself is ALWAYS enforced SERVER-SIDE (the module edge's
  // `resolve_scope_access` returns only in-scope rows from `GET /members`); the
  // region text filter is purely a client-side narrowing of the already-scoped
  // rows and NEVER invents scope. The filter is wired through the shared
  // `useFilterableTable` on the `region` key, so it applies IN EVERY view
  // context (a context chooses columns, never rows).
  const scopeDimension = useMemo<ScopeDimension | undefined>(() => {
    const dims = fieldConfig?.dimensions ?? [];
    // Prefer the `region` dimension (h-dcn's one wired dimension); otherwise the
    // first enabled dimension the tenant authored.
    return (
      dims.find(d => d.key === 'region')
      ?? dims.find(d => d.enabled !== false)
    );
  }, [fieldConfig]);

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

  // The RAW user-chosen column keys (session-columns C6). A key the user
  // explicitly surfaced via the chooser is treated as filterable even when the
  // active context defines a `filterable_columns` allow-list that omits it — the
  // user asked to work with it (R2.1). Built from `chosenKeys` (the raw user
  // selection), NOT `effectiveChosenKeys`/the first-time default, so only the
  // user's OWN picks earn the exemption; member_number stays filterable as today.
  const chosenKeySet = useMemo(() => new Set(chosenKeys), [chosenKeys]);

  const isFilterable = useCallback(
    (key: string): boolean =>
      (filterableSet ? filterableSet.has(key) || chosenKeySet.has(key) : true),
    [filterableSet, chosenKeySet],
  );

  // Build flat rows; promote the region display value for the region column + stats.
  const memberRows: MemberRow[] = useMemo(
    () => members.map(m => ({
      ...m,
      region_display: (m.region as string) || '',
    })),
    [members],
  );

  // ── Unified column model (session-columns task 4.2, design C3; R1.2, R1.3, ────
  //    R4.4, R7.1, R7.3) ─────────────────────────────────────────────────────────
  // One ordered column model replaces BOTH legacy render paths (the explicit-
  // columns `contextColumns` path AND the compact/full `COMPACT_FIELD_KEYS` +
  // overlay path). `columns = [member_number] ⊕ chosenColumns`, rendered by a
  // single header map + a single cell map, so every column flows through
  // identical FilterableHeader wiring (full unification, OQ-2).
  //
  // Fast lookup of every resolved field descriptor by key.
  const fieldByKey = useMemo(
    () => new Map<string, FieldConfigField>(
      (fieldConfig?.fields ?? []).map(f => [f.key, f]),
    ),
    [fieldConfig],
  );

  // The admin default/compact column KEYS a FIRST-TIME user (empty `chosenKeys`)
  // sees (R6.4 / OQ-A → (a)): when the active context has no explicit `columns`,
  // the hardcoded compact set + `region` + (in full view) the overlay fields;
  // when the context DOES define `columns`, exactly those context keys. Once the
  // user saves a selection their own list is authoritative and this is unused.
  const defaultColumnKeys: string[] = useMemo(() => {
    if (hasExplicitColumns) {
      return contextColumns.map(f => f.key);
    }
    const overlayKeys = viewMode === 'full' ? overlayFields.map(f => f.key) : [];
    // The compact set carries member_number first; it is prepended separately by
    // the model below, so drop it here to avoid a duplicate. `region` is a
    // dimension-backed column (no field descriptor needed) surfaced after the
    // compact fixed fields, exactly as the legacy compact path did.
    const compact = COMPACT_FIELD_KEYS.filter(k => k !== MEMBER_NUMBER_KEY);
    return [...compact, 'region', ...overlayKeys];
  }, [hasExplicitColumns, contextColumns, viewMode, overlayFields]);

  // The user's effective chosen keys: THEIR saved list when non-empty, else the
  // first-time admin default (above). A context switch does NOT rebuild a saved
  // user's list (OQ-1) — `chosenKeys` is owned by the user; the context only
  // feeds the default when the user has none, plus default_sort / filterable_
  // columns / page_size elsewhere.
  const effectiveChosenKeys: string[] = useMemo(
    () => (chosenKeys.length > 0 ? chosenKeys : defaultColumnKeys),
    [chosenKeys, defaultColumnKeys],
  );

  // Resolve the member_number descriptor (R7.1). Prefer the field-config
  // descriptor; fall back to a synthesized one so the leading column always
  // renders even when the config omits member_number (the legacy compact path
  // hardcoded it). It is pinned first + never removable, so it never appears in
  // the chosen list (R7.3).
  const memberNumberColumn: OverviewColumn = useMemo(
    () => ({ field: fieldByKey.get(MEMBER_NUMBER_KEY) ?? { key: MEMBER_NUMBER_KEY } }),
    [fieldByKey],
  );

  // `chosenColumns` — `effectiveChosenKeys` resolved to column descriptors,
  // de-duped, with member_number excluded (it is prepended separately, R7.3).
  // A key with a field descriptor that is NOT a candidate (visible === false) is
  // skipped (R5.1). `region` has no field descriptor but is still a valid column
  // (dimension-backed): a key with no descriptor is kept with a synthesized
  // descriptor so it renders (its value resolves via region_display / valueFor).
  const chosenColumns: OverviewColumn[] = useMemo(() => {
    const seen = new Set<string>([MEMBER_NUMBER_KEY]);
    const resolved: OverviewColumn[] = [];
    for (const key of effectiveChosenKeys) {
      if (!key || seen.has(key)) continue;
      const field = fieldByKey.get(key);
      // A configured field that is explicitly not a candidate is dropped.
      if (field && !isColumnCandidate(field)) continue;
      seen.add(key);
      resolved.push({ field: field ?? { key } });
    }
    return resolved;
  }, [effectiveChosenKeys, fieldByKey]);

  // The final ordered column model: member_number ALWAYS first (R7.1), then the
  // chosen columns. ONE source of truth for both the header map + the cell map.
  const columns: OverviewColumn[] = useMemo(
    () => [memberNumberColumn, ...chosenColumns],
    [memberNumberColumn, chosenColumns],
  );

  // Resolve a column's header label (session-columns C3). member_number keeps
  // its legacy i18n label unconditionally (it is the pinned fixed column). The
  // other fixed compact keys (name/email/status/membership_type/region) keep
  // their legacy i18n label ONLY in the default/compact path — matching the
  // pre-unification compact render path; in an EXPLICIT-columns context those
  // keys resolve through the field-config label exactly as the legacy explicit
  // path did (so e.g. `email` renders "E-mail", `region` renders "Regio"). Every
  // other column always uses its field-config `resolveLabel`.
  const columnLabel = useCallback(
    (field: FieldConfigField): string => {
      if (field.key === MEMBER_NUMBER_KEY) {
        return t(FIXED_COLUMN_LABEL_KEYS[MEMBER_NUMBER_KEY]);
      }
      const legacyKey = FIXED_COLUMN_LABEL_KEYS[field.key];
      if (legacyKey && !hasExplicitColumns) return t(legacyKey);
      // In an explicit context, `region` has a field descriptor; the compact
      // default's dimension-backed `region` has none — fall back to its legacy
      // i18n label so it is never a bare key.
      if (field.key === 'region' && !fieldByKey.has('region')) {
        return t(FIXED_COLUMN_LABEL_KEYS.region);
      }
      return resolveLabel(field.label, lang, field.key);
    },
    [t, lang, hasExplicitColumns, fieldByKey],
  );

  // Resolve a column's cell value for a row. member_number + region keep their
  // legacy accessors (the flat alias / dimension display); every other column
  // renders through the shared nested-aware accessor + presenter (valueFor +
  // renderFieldValue), identical to the legacy explicit-columns path.
  const renderCell = useCallback(
    (field: FieldConfigField, row: MemberRow): React.ReactNode => {
      if (field.key === MEMBER_NUMBER_KEY) return (row.member_number as string) || '-';
      if (field.key === 'region') return row.region_display || '-';
      return renderFieldValue(field, valueFor(row, field.group, field.key), lang);
    },
    [lang],
  );

  // Every candidate field (visible !== false) the global search scans — the fixed
  // base ⊕ overlay ⊕ calculated union, resolved from the field config. The value
  // of each is read with the nested-aware `valueFor` accessor, so a nested
  // overlay / calculated field (e.g. a derived membership duration) is searchable
  // even though the overview never renders it as a flat column.
  const searchableFields: FieldConfigField[] = useMemo(
    () => (fieldConfig?.fields ?? []).filter(isColumnCandidate),
    [fieldConfig],
  );

  // Narrow the rows by the global search BEFORE the per-column filter/sort
  // toolkit. A row matches when ANY candidate field's resolved value contains the
  // query (case-insensitive substring). An empty query is a pass-through (no
  // allocation of a new array content beyond the memo). Scope is never widened —
  // this only ever removes rows from the already-authorized set.
  const searchedRows: MemberRow[] = useMemo(() => {
    const q = globalSearch.trim().toLowerCase();
    if (q === '') return memberRows;
    return memberRows.filter(row =>
      searchableFields.some(f => {
        const value = valueFor(row, f.group, f.key);
        if (value === null || value === undefined) return false;
        return String(value).toLowerCase().includes(q);
      }),
    );
  }, [memberRows, searchableFields, globalSearch]);

  // ── On-the-fly flatten (session-columns task 4.3, design C4; R2.2, R2.3, ──────
  //    R2.5, R3.4) ───────────────────────────────────────────────────────────────
  // Promote each chosen NON-ALIAS column key to a flat top-level property on the
  // row — the flat-key rule (see `valueFor`): a column filters/sorts iff its key
  // is a flat `row[key]`. The chosen field's RESOLVED value (nested-aware
  // `valueFor`) is coerced by the field `type` (`coerceByType`) so the sort
  // compares a real number / chronological date rather than a lexical string
  // (R2.3); the filter engine still stringifies for its case-insensitive match.
  //
  // Flat aliases (`member_number, name, email, status, membership_type, region,
  // membership_id`) are SKIPPED via `shouldFlatten` so a chosen key that happens
  // to be one of `flattenMember`'s carefully-mapped aliases is never clobbered
  // (R3.4). region is a flat alias, so a chosen `region` is left as-is.
  //
  // COMPOSITION (R2.5): this maps over `searchedRows` — the global search runs
  // FIRST, then the surviving rows are flattened — and the ENRICHED result (not
  // `searchedRows`) feeds `useFilterableTable`. Both are pure row transforms;
  // search-then-flatten minimizes per-keystroke work. Presentation-only: it only
  // adds flat keys to already scope-authorized rows, never widening scope.
  const enrichedRows: MemberRow[] = useMemo(() => {
    const promotable = chosenColumns
      .map(c => c.field)
      .filter(f => shouldFlatten(f.key));
    if (promotable.length === 0) return searchedRows;
    return searchedRows.map(row => {
      const extra: Record<string, unknown> = {};
      for (const f of promotable) {
        extra[f.key] = coerceByType(f, valueFor(row, f.group, f.key));
      }
      return { ...row, ...extra };
    });
  }, [searchedRows, chosenColumns]);

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

  // ── Dynamic filter key set (session-columns task 4.4, design C5; R2.1, ────────
  //    R2.4, R4.3) ────────────────────────────────────────────────────────────
  // `useFilterableTable` is handed `initialFilters` = the fixed keys PLUS each
  // chosen column key (empty string each), so every shown column has a filter
  // slot. member_number is already in INITIAL_FILTERS; the rest of `columns`
  // (i.e. `chosenColumns`) each add their key. We RELY on `useColumnFilters`
  // reconciling on the key-set signature (findings F-007): when the user adds /
  // removes a column the key set changes, so its filter input is added / its
  // value dropped automatically — no hook change, no manual cleanup. The memo's
  // dependency is the chosen column KEY LIST, so a changed set rebuilds the
  // object (and shifts the key-set signature the hook watches).
  const dynamicInitialFilters = useMemo(() => {
    const next: Record<string, string> = { ...INITIAL_FILTERS };
    for (const { field } of chosenColumns) {
      if (!(field.key in next)) next[field.key] = '';
    }
    return next;
    // Keyed on the chosen column keys so the memo only rebuilds when the set
    // of shown columns actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosenColumns.map(c => c.field.key).join('\u241F')]);

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
  // types a column filter, sorts, or SWITCHES VIEW
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

      // Columns are driven by the SAME resolved field config the view modal uses (R4.9): the
      // full visible field set (fixed base ⊕ overlay ⊕ calculated), sectioned by
      // functional_group in the same order, flattened into a single column list. `formFields`
      // already omits the internal `member_id` UUID + system timestamps (s5k R1 — member_id is
      // never exported), and each cell resolves through the shared nested-shape accessor
      // (`valueFor`) + presenter (`renderFieldValue`), so the CSV carries the REAL Lidnummer and
      // every personal/overlay/calculated field — exactly what the modal shows. show_when is a
      // per-member predicate; a CSV needs a uniform column set, so we include every visible field
      // as a column and let an absent value render as the placeholder dash.
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
  // trailing selection column. One source now that both legacy paths collapse
  // into `columns` (design C3).
  const colSpan = columns.length + 1;

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
          {/* Column chooser action (session-columns task 4.1, R1/C2) — opens the
              ColumnChooser modal; the user picks which candidate fields show as
              columns. Right-aligned, ghost, same header pattern as Export. */}
          <Button
            size="sm"
            leftIcon={<SettingsIcon />}
            colorScheme="orange"
            variant="ghost"
            onClick={onColumnChooserOpen}
            data-testid="members-column-chooser-button"
          >
            {t('columnChooser.button')}
          </Button>
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

      {/* Global all-fields search (member-field-search Option 1). Narrows the
          rows across EVERY candidate field (incl. non-visible overlay/calculated
          fields) before the per-column filter/sort toolkit, so the stats strip
          and table below follow automatically. */}
      {!loading && (
        <Box mb={4} maxW="md">
          <InputGroup size="sm">
            <InputLeftElement pointerEvents="none">
              <SearchIcon color="gray.400" boxSize="12px" />
            </InputLeftElement>
            <Input
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
              placeholder={t('search.placeholder')}
              aria-label={t('search.ariaLabel')}
              bg="gray.800"
              color="white"
              _placeholder={{ color: 'gray.400' }}
              borderColor="gray.600"
              autoComplete="off"
              data-testid="members-global-search"
            />
            {globalSearch !== '' && (
              <InputRightElement>
                <IconButton
                  size="xs"
                  variant="ghost"
                  colorScheme="orange"
                  aria-label={t('search.clear')}
                  icon={<CloseIcon boxSize="8px" />}
                  onClick={() => setGlobalSearch('')}
                  data-testid="members-global-search-clear"
                />
              </InputRightElement>
            )}
          </InputGroup>
        </Box>
      )}

      {/* Live statistics strip (task 4.3, design C-SURFACE; R5.4) — reuses the
          shared stats-strip convention (steering 32; `bg="gray.800"` cards, same
          shape as MediaAssetAdmin's `StatCard`). Built from plain `Box`/`Text`
          rather than Chakra's `Stat`/`StatLabel`/`StatNumber`: the `Stat*` family
          resolves to `undefined` under the test runner's ESM interop (it would
          crash the whole page with "Element type is invalid"), whereas
          `Box`/`Text` render identically in-app and under test. Every figure is
          recomputed from `processedData` (the filtered+sorted rows), so the strip
          follows every column filter, sort, and view-context switch. */}
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
              // functional_group, honoring visibility + show_when. The internal member_id (UUID)
              // is NOT shown — the human-facing Lidnummer (member_number) already renders in the
              // Membership/Lidmaatschap group; showing the UUID here was a mislabeled duplicate.
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

      {/* Column chooser modal (session-columns task 4.1, design C2/C8). Renders
          every candidate field via the shared FieldChecklist; the user's picks
          (minus the always-on member_number) drive `chosenKeys`. Each change is
          applied optimistically AND persisted (handleColumnsChange). The column
          model that CONSUMES `chosenKeys` is task 4.2. */}
      <ColumnChooser
        isOpen={isColumnChooserOpen}
        onClose={onColumnChooserClose}
        fieldConfig={fieldConfig}
        selectedKeys={chosenKeys}
        language={lang}
        onChange={handleColumnsChange}
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
