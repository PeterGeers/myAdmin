/**
 * MemberAnalyticsPage — the Member Analytics surface for the Members module.
 *
 * A separate page/route beside the member table (Leden Overzicht), hosting the
 * Overview summary, violin distributions, and pivot/list views with
 * CSV / PDF-label / SES-mail exports. All views are computed over the page's
 * own scope-authorized, filtered member set.
 *
 * Task 3.1 scope: the page shell + route registration + the `members:read`
 * capability gate, following the dark-theme / orange-primary Chakra
 * conventions in steering 32 and the `STRReports.tsx` / `FINReports.tsx`
 * report-group pattern.
 *
 * Task 3.2 scope (THIS task): the page fetches its OWN scope-authorized data
 * (R1.5, R5.1) and mounts its OWN self-contained filter (Option A):
 *   - `listMembers()` → flattened `memberRows` (nested buckets retained for the
 *     shared `valueFor` accessor + the flat compact-column aliases), with
 *     loading + error handling;
 *   - `getFieldConfig()` → `FieldConfig` (incl. the analytics config block),
 *     resolved independently (a field-config miss does not fail the page);
 *   - its OWN `useFilterableTable(memberRows)` instance — NOT shared with the
 *     main member table (separate page, no cross-page filter state, R4.4a) —
 *     with its own `FilterableHeader` filter controls, exactly as the member
 *     table wires them (so scope-authorization / tenant isolation are preserved:
 *     the page only ever narrows WITHIN the scope-narrowed `GET /members` set,
 *     never invents scope, R5.1).
 *
 * The `processedData` this produces (the page's own filtered dataset) is the
 * single source the view-switch panel + three areas consume.
 *
 * Task 3.4 scope (THIS task): the THREE non-happy states, rendered DISTINCTLY so
 * a user can tell them apart (R1.4), never a crash:
 *   1. **Empty set** — the scope-authorized / filtered set has zero rows. A
 *      NEUTRAL empty state (`analytics-empty`, `analytics.states.empty`) in place
 *      of the analytics panel — explicitly not an error. Shown both when the
 *      initial scoped set is empty and when the page's own filter narrows to
 *      zero rows.
 *   2. **No analytics config** — the tenant has not authored the analytics
 *      config (R9). The fixed/calculated areas (Overview, Distributions over
 *      age/years_member) still render; the config-DEPENDENT sets degrade with a
 *      bilingual reason inside the Pivot Views area (`analytics.degradation.*`),
 *      never an error. Signalled by the `hasAnalyticsConfig` flag derived here
 *      and plumbed to the panel.
 *   3. **Load failure** — `GET /members` failed. An explicit ERROR state
 *      (`analytics-load-error`, `analytics.states.loadError`) with a retry
 *      affordance, visually + semantically distinct from the neutral empty state.
 *
 * Capability gate (R1.2): visible only to a caller holding `members:read`,
 * which maps to the `Members_Read` role (the same gate the member table uses,
 * `['Members_Read', 'Members_CRUD']`). The page is read-only — it introduces
 * no member write/mutate action.
 *
 * @module pages/MemberAnalyticsPage
 * @see .kiro/specs/Members/member-analytics (design C1; requirements R1.1, R1.2, R1.5, R5.1)
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box, VStack, HStack, Flex, Heading, Text, Alert, AlertIcon, Spinner, Button,
  Table, Thead, Tr,
} from '@chakra-ui/react';
import { RepeatIcon } from '@chakra-ui/icons';
import { useAuth } from '../context/AuthContext';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';
import { listMembers, getFieldConfig } from '../services/membersApiService';
import type { Member, MemberRow, FieldConfig, LocalizedLabel } from '../types/members';
import { MemberAnalyticsPanel, hasAnalyticsConfig, assessDataVolume } from '../components/members/analytics';
import AnalyticsStateNotice from '../components/members/analytics/areas/AnalyticsStateNotice';

/** Roles that satisfy the `members:read` capability for this page (R1.2). */
const MEMBERS_READ_ROLES = ['Members_Read', 'Members_CRUD'];

/**
 * Roles that satisfy the `members:export` capability — the gate for the result
 * exports (CSV / PDF labels / mail) that live in the Pivot Views area. Mirrors
 * the member table, where CRUD-capable callers can export the scoped rows.
 */
const MEMBERS_EXPORT_ROLES = ['Members_Export', 'Members_CRUD'];

/**
 * Roles that satisfy the `members:write` capability — CRUD authors (R11). A
 * write-capable caller may CREATE a shared analytics-set and EDIT one; combined
 * with `members:export` it gates the create/edit set actions in Pivot Views.
 */
const MEMBERS_WRITE_ROLES = ['Members_CRUD'];

/**
 * Roles that satisfy the `members:admin` capability — the tenant administrator.
 * This alone grants permanently DELETING a saved set from the shared library.
 */
const MEMBERS_ADMIN_ROLES = ['Tenant_Admin'];

/**
 * The DELETE-a-saved-set gate (UI). A set may be permanently deleted only by a
 * privileged caller: a Tenant_Admin, OR a tenant-wide CRUD caller — i.e. one who
 * holds BOTH `Regio_All` (tenant-wide scope) AND `Members_CRUD` (write). A
 * region-scoped CRUD caller (Members_CRUD without Regio_All) can add/edit sets
 * but CANNOT delete. Rule: (Regio_All AND Members_CRUD) OR Tenant_Admin.
 */
const MEMBERS_DELETE_ALL_SCOPE_ROLE = 'Regio_All';
const MEMBERS_DELETE_WRITE_ROLE = 'Members_CRUD';

/**
 * The analytics filter columns, mirroring the member table's compact-column
 * filter set so the page filters the SAME scope-authorized fields the table
 * does (member number / name / email / status / type + the region scope
 * dimension). This is the page's OWN filter model (Option A) — a fresh
 * `useFilterableTable` instance, never shared with `MembersPage` (R4.4a).
 */
const INITIAL_FILTERS: Record<string, string> = {
  member_number: '',
  name: '',
  email: '',
  status: '',
  membership_type: '',
  region: '',
};

/**
 * The analytics filter columns in display order. `labelKey` is a `columns.*`
 * i18n key (bilingual, from task 0.3's namespace), used as the fallback when the
 * resolved field config does not carry a label for the field — no hardcoded
 * English (R6.4).
 */
const FILTER_COLUMNS: { key: string; labelKey: string }[] = [
  { key: 'member_number', labelKey: 'columns.memberNumber' },
  { key: 'name', labelKey: 'columns.name' },
  { key: 'email', labelKey: 'columns.email' },
  { key: 'status', labelKey: 'columns.status' },
  { key: 'membership_type', labelKey: 'columns.membershipType' },
  { key: 'region', labelKey: 'columns.region' },
];

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

const MemberAnalyticsPage: React.FC = () => {
  const { t, i18n } = useTypedTranslation('members');
  const { user } = useAuth();
  const lang = (i18n?.language || 'nl').slice(0, 2);

  // Capability gate (R1.2): require `members:read` (Members_Read / Members_CRUD).
  const canReadMembers = user?.roles?.some(role => MEMBERS_READ_ROLES.includes(role));
  // Export capability (`members:export`) — gates the result exports in the Pivot
  // Views area; plumbed to the panel as `capabilities.canExport`.
  const canExport = !!user?.roles?.some(role => MEMBERS_EXPORT_ROLES.includes(role));
  // Write capability (`members:write`, Members_CRUD) + admin (`members:admin`,
  // Tenant_Admin) — gate the shared analytics-set create/edit/delete actions in
  // the Pivot Views area (R11: create = export|write, delete = write|admin).
  const canWrite = !!user?.roles?.some(role => MEMBERS_WRITE_ROLES.includes(role));
  // Delete gate (UI): (Regio_All AND Members_CRUD) OR Tenant_Admin. Passed as the
  // panel's `isAdmin` flag, which is what gates the delete action there. Plain
  // Members_CRUD (region-scoped) can add/edit but NOT delete.
  const roles = user?.roles ?? [];
  const isTenantAdmin = roles.some(role => MEMBERS_ADMIN_ROLES.includes(role));
  const isTenantWideCrud =
    roles.includes(MEMBERS_DELETE_ALL_SCOPE_ROLE) &&
    roles.includes(MEMBERS_DELETE_WRITE_ROLE);
  const isAdmin = isTenantAdmin || isTenantWideCrud;

  // ── The page's OWN data (R1.5): it fetches the scope-authorized member set and
  //    field config itself, since it is a SEPARATE page from the member table. ──
  const [members, setMembers] = useState<Member[]>([]);
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // Load the scope-authorized member set via the SAME `listMembers()` the table
  // uses — so the rows are exactly the server-side scope-narrowed set (R5.1); the
  // page never widens that set, it only narrows it further with its own filter.
  const loadMembers = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const rows = await listMembers<Member[]>();
      setMembers(Array.isArray(rows) ? rows : []);
    } catch {
      setMembers([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // Resolve the field config (incl. the analytics config block) independently: a
  // field-config miss degrades gracefully (fixed/calculated areas still work,
  // config-dependent sets degrade in 3.4) rather than failing the whole page.
  const loadFieldConfig = useCallback(async () => {
    try {
      const cfg = await getFieldConfig<FieldConfig>();
      setFieldConfig(cfg ?? null);
    } catch {
      setFieldConfig(null);
    }
  }, []);

  // Fetch both on open (R1.6 — immediate). Only the member-list load gates the
  // page's loading/error state; the field config layers in when it resolves.
  const loadAll = useCallback(() => {
    void loadMembers();
    void loadFieldConfig();
  }, [loadMembers, loadFieldConfig]);

  useEffect(() => {
    if (canReadMembers) loadAll();
  }, [canReadMembers, loadAll]);

  // Flat rows for the filter framework; promote the region display value for the
  // region column + filter (mirrors `MembersPage`'s `memberRows`).
  const memberRows: MemberRow[] = useMemo(
    () => members.map(m => ({
      ...m,
      region_display: (m.region as string) || '',
    })),
    [members],
  );

  // Resolve a filter column's label from the field config (bilingual
  // `{nl,en}`), the same way the table resolves field labels. Returns undefined
  // when the field config has not resolved / lacks the field, so the caller
  // falls back to the `columns.*` i18n key (R6.4 — never a raw/hardcoded label).
  const labelByKey = useMemo(() => {
    const map = new Map<string, string | LocalizedLabel | undefined>();
    for (const f of fieldConfig?.fields ?? []) map.set(f.key, f.label);
    return map;
  }, [fieldConfig]);

  const fieldLabel = useCallback(
    (key: string): string | LocalizedLabel | undefined => labelByKey.get(key),
    [labelByKey],
  );

  // ── The page's OWN `useFilterableTable` instance (Option A, self-contained) ──
  // A FRESH instance over `memberRows` — NOT shared with the member table. Its
  // `processedData` is the page's own filtered dataset that feeds the Overview /
  // Distributions / Pivot areas in 3.3+. Default sort mirrors the table (name asc).
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

  // The "no analytics config" signal (R1.4, state 2): whether the tenant
  // authored any analytics config block. Derived once here and plumbed to the
  // panel so the config-dependent sets degrade with a reason while the
  // fixed/calculated areas keep working. NOT an error/empty signal.
  const analyticsConfigPresent = useMemo(
    () => hasAnalyticsConfig(fieldConfig),
    [fieldConfig],
  );

  // Whether the page's own filtered dataset is empty (R1.4, state 1) — drives
  // the NEUTRAL empty state that replaces the analytics panel, kept distinct
  // from the load-failure error state (state 3).
  const isEmpty = processedData.length === 0;

  // ── Data-volume guard (C8, R7.1/R7.3/R7.4) ────────────────────────────────
  // Measure the SERIALIZED byte length of the scope-authorized `GET /members`
  // set (the full `members` payload, NOT the post-filter `processedData` — the
  // guard is about the response the module returned, which Option 2 aggregates
  // over). Measured once per load (memoized on `members`), not per filter
  // keystroke. The assessment classifies the size against the 6 MiB Lambda
  // ceiling and, at the warning/exceeded levels, emits a PII-free operational
  // signal as a side effect (console.warn / metric seam, R7.3 / R8.3).
  const dataVolume = useMemo(() => assessDataVolume(members), [members]);

  // Capability gate first — a caller without `members:read` sees only the notice.
  if (!canReadMembers) {
    return (
      <Box p={6} bg="gray.800" minH="100vh">
        <Alert status="warning">
          <AlertIcon />
          {t('analytics.noPermission')}
        </Alert>
      </Box>
    );
  }

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <Box>
          <Heading size="lg" color="orange.400">
            {t('analytics.title')}
          </Heading>
          <Text color="gray.400" mt={1}>
            {t('analytics.subtitle')}
          </Text>
        </Box>

        {loading ? (
          // Fetch in flight — the page's own member-set load.
          <HStack color="white" data-testid="analytics-loading">
            <Spinner color="orange.300" />
            <Text>{t('table.loading')}</Text>
          </HStack>
        ) : loadError ? (
          // Load failure (R1.4 — distinct from "empty"): an explicit error state
          // with a retry affordance. The richer three-state rendering is 3.4.
          <Alert
            status="error"
            variant="subtle"
            flexDirection="column"
            alignItems="flex-start"
            gap={3}
            bg="gray.900"
            borderWidth="1px"
            borderColor="red.700"
            borderRadius="md"
            data-testid="analytics-load-error"
          >
            <HStack>
              <AlertIcon />
              <Text color="white">{t('analytics.states.loadError')}</Text>
            </HStack>
            <Button
              size="sm"
              leftIcon={<RepeatIcon />}
              colorScheme="orange"
              onClick={loadAll}
            >
              {t('analytics.states.retry')}
            </Button>
          </Alert>
        ) : (
          <>
            {/* The page's OWN filter bar (Option A). Reuses the member table's
                `FilterableHeader` controls, so the filter behavior mirrors the
                table — but over this page's own `useFilterableTable` instance,
                with no cross-page filter state. The scope dimension (region) and
                the compact identity/status/type columns are filterable. */}
            <Box overflowX="auto" data-testid="analytics-filter-bar">
              <Table variant="simple" size="sm" bg="gray.800" color="white">
                <Thead>
                  <Tr>
                    {FILTER_COLUMNS.map(col => (
                      <FilterableHeader
                        key={col.key}
                        label={resolveLabel(fieldLabel(col.key), lang, t(col.labelKey))}
                        filterValue={filters[col.key] ?? ''}
                        onFilterChange={(v) => setFilter(col.key, v)}
                        placeholder={t('filters.placeholder')}
                        sortable
                        sortDirection={columnSortDirection(col.key)}
                        onSort={() => handleSort(col.key)}
                      />
                    ))}
                  </Tr>
                </Thead>
              </Table>
            </Box>

            {/* Live count of the page's own filtered dataset (`processedData`).
                Confirms the own-filter wiring end to end; the view-switch panel
                (Overview / Distributions / Pivot Views) consuming `processedData`,
                `members`, and `fieldConfig` mounts here in 3.3. */}
            <Flex gap={4} wrap="wrap" data-testid="analytics-count-strip">
              <Box bg="gray.900" borderRadius="md" px={4} py={2}>
                <Text fontSize="xs" color="gray.400">
                  {t('analytics.overview.stats.count')}
                </Text>
                <Text fontSize="lg" fontWeight="bold" color="orange.300" data-testid="analytics-row-count">
                  {processedData.length}
                </Text>
              </Box>
            </Flex>

            {dataVolume.exceeded ? (
              /* Data-volume guard — OVER the 6 MiB limit (C8, R7.4): the
                 scope-authorized `GET /members` response is at/over the hard AWS
                 Lambda limit, so it is (or would be) truncated. We render an
                 explicit "dataset too large" state and run NO partial
                 aggregation — the analytics panel does not mount its areas, so
                 no figure is ever computed over a silently-partial set. Rendered
                 as an ERROR-level alert (not the neutral empty notice), accessible
                 via icon + text (not colour alone, R6.6), bilingual via
                 `analytics.overLimit.exceeded`. */
              <Alert
                status="error"
                variant="subtle"
                flexDirection="row"
                alignItems="center"
                gap={2}
                bg="gray.900"
                borderWidth="1px"
                borderColor="red.700"
                borderRadius="md"
                data-testid="analytics-over-limit-exceeded"
              >
                <AlertIcon />
                <Text color="white">{t('analytics.overLimit.exceeded')}</Text>
              </Alert>
            ) : isEmpty ? (
              /* State 1 — Empty set (R1.4): the scope-authorized / filtered set
                 has zero rows. A NEUTRAL empty state in place of the analytics
                 panel, distinct from the load-failure error state (state 3): an
                 info icon + bilingual text, `role="status"` (not an alert), so
                 the user reads it as "nothing to show here", not "something
                 broke". The filter bar above stays mounted so the user can widen
                 the filter back out. */
              <AnalyticsStateNotice kind="empty" message={t('analytics.states.empty')} />
            ) : (
              /* Below the limit — the analytics panel renders. When the set is in
                 the WARNING band (≥ 80% of 6 MiB, C8/R7.3) a user-visible warning
                 banner precedes the panel: results may be incomplete, but the
                 aggregation still runs (distinct from the exceeded state). The
                 banner is an alert with icon + bilingual text (not colour alone,
                 R6.6). */
              <>
                {dataVolume.showWarning && (
                  <Alert
                    status="warning"
                    variant="subtle"
                    flexDirection="row"
                    alignItems="center"
                    gap={2}
                    bg="gray.900"
                    borderWidth="1px"
                    borderColor="yellow.700"
                    borderRadius="md"
                    mb={4}
                    data-testid="analytics-over-limit-warning"
                  >
                    <AlertIcon />
                    <Text color="white">{t('analytics.overLimit.warning')}</Text>
                  </Alert>
                )}
                {/* The view-switch panel (task 3.3): one area visible at a time
                    (Overview default), each area lazy-mounted on selection (R1.6).
                    It consumes the page's OWN filtered dataset (`processedData`),
                    the full scope-authorized `members`, the resolved `fieldConfig`,
                    the `hasAnalyticsConfig` degradation signal (state 2), the active
                    `language`, and the caller `capabilities`. */}
                <Box
                  bg="gray.900"
                  borderWidth="1px"
                  borderColor="gray.700"
                  borderRadius="md"
                  p={6}
                >
                  <MemberAnalyticsPanel
                    processedData={processedData}
                    members={members}
                    fieldConfig={fieldConfig}
                    hasAnalyticsConfig={analyticsConfigPresent}
                    language={lang}
                    capabilities={{ canExport, canWrite, isAdmin }}
                  />
                </Box>
              </>
            )}
          </>
        )}
      </VStack>
    </Box>
  );
};

export default MemberAnalyticsPage;
