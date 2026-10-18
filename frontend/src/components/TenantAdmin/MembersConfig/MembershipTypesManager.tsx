/**
 * Membership-type catalog management surface (membership-type-catalog-admin-ui, task 2.1 — LIST SURFACE).
 *
 * A TenantAdmin "Lidmaatschapstypes" surface that lists the tenant's membership-type catalog — the
 * authoring door that was missing for the LIVE `membership_type` reference field. It reads ALL entries
 * (incl. retired) via `listMembershipTypes()` (NO active filter — R1.2) and renders a table of
 * `type_code` / bilingual `label` / `active` state / `order`, sorted by `(order, type_code)` ascending.
 * An empty tenant renders a friendly bilingual empty state WITH a create action — never a crash (R1.4).
 *
 * ## Scope of THIS task (2.1) — list surface only
 *
 * This component owns the LIST + EMPTY STATE + a create ACTION button, matching the `MembersConfigEditor`
 * house style (Chakra, the `t(nl,en)` bilingual helper, `useToast`, loading `Spinner`, error
 * `Text color="red.300"`, best-effort load with try/catch, `data-testid` conventions). The mutation
 * surfaces that follow are left as CLEAN SEAMS for sibling tasks:
 *
 *   - `onCreate?()`       — the create-button seam (task 2.2 wires the create modal).
 *   - `onEdit?(typeCode)` — the row-level edit seam (task 2.2 wires the edit modal; row-click opens it,
 *                           per the frontend row-click-opens-modal convention).
 *   - task 2.3 owns client-side pre-submit validation + server-error surfacing (in the modal).
 *   - task 2.5 owns the component tests (this file ships testable `data-testid`s, no test here).
 *
 * The create/edit handlers default to a harmless no-op + toast stub so the surface is self-contained
 * and never dead until 2.2 passes real handlers in.
 *
 * ## Admin-capability gate (TASK 2.4 — UX ONLY; SAM is authoritative)
 *
 * The catalog mutations (create / edit / retire) require the Members admin capability (`members:admin`),
 * which the SAM `CATALOG` write routes (`POST`/`PUT`/`DELETE /membership-types`) enforce AUTHORITATIVELY
 * on every call — a non-admin's write is rejected server-side with a 403 regardless of what the UI shows.
 * This component additionally GATES the mutation affordances for UX (R1.3 — "a non-admin SHALL NOT see
 * the management actions"), mirroring `pages/MemberAnalyticsPage.tsx`: `Tenant_Admin` satisfies
 * `members:admin`, read off the authenticated `user.roles` from `useAuth()`.
 *
 * This is purely a convenience layer — it does NOT touch the service wrappers and is NEVER relied on for
 * security. A non-admin still SEES the read-only list (R1.1/R1.2), but WITHOUT the create button(s) and
 * with rows that do not open the mutation modal. Were a mutation ever attempted anyway, the SAM 403 still
 * surfaces readably via `applyApiError` (task 2.3).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Badge,
  Box,
  Button,
  HStack,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  useToast,
} from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../../context/AuthContext';
import { listMembershipTypes } from '../../../services/members/membersConfigApi';
import { resolveFieldConfigLabel } from '../../../services/membersConfigService';
import type { MembershipType } from '../../../types/members';
import { MembershipTypeModal, type MembershipTypeModalMode } from './MembershipTypeModal';

interface Props {
  tenant: string;
  /**
   * OPTIONAL create-action OVERRIDE. By default (task 2.2) the create button opens this surface's
   * own `MembershipTypeModal` in create mode. A parent may pass `onCreate` to intercept instead
   * (e.g. to route elsewhere); when provided it fully replaces the default modal-open behaviour.
   */
  onCreate?: () => void;
  /**
   * OPTIONAL row-level edit OVERRIDE. By default (task 2.2) a row-click opens the edit modal
   * pre-filled with that entry. A parent may pass `onEdit(typeCode)` to intercept instead; when
   * provided it fully replaces the default modal-open behaviour.
   */
  onEdit?: (typeCode: string) => void;
}

/**
 * Roles that satisfy the `members:admin` capability for the catalog mutations (R1.3). Mirrors
 * `pages/MemberAnalyticsPage.tsx` (`MEMBERS_ADMIN_ROLES = ['Tenant_Admin']`) — the same role→capability
 * mapping, kept identical so the two surfaces gate `members:admin` the same way. SAM stays authoritative.
 */
const MEMBERS_ADMIN_ROLES = ['Tenant_Admin'];

/** The catalog reference code for an entry — `type_code` is authoritative, `key` a legacy alias. */
function codeOf(entry: MembershipType): string {
  return entry.type_code ?? entry.key ?? '';
}

/**
 * Sort by `(order, type_code)` ascending (R1.2). `order` is an integer (server defaults 0); a
 * missing order sorts as 0. Ties break on `type_code` (locale-aware, case-insensitive-ish).
 */
function sortCatalog(entries: MembershipType[]): MembershipType[] {
  return [...entries].sort((a, b) => {
    const orderA = typeof a.order === 'number' ? a.order : 0;
    const orderB = typeof b.order === 'number' ? b.order : 0;
    if (orderA !== orderB) return orderA - orderB;
    return codeOf(a).localeCompare(codeOf(b));
  });
}

export const MembershipTypesManager: React.FC<Props> = ({ tenant, onCreate, onEdit }) => {
  const { i18n } = useTranslation();
  const lang = (i18n.language?.startsWith('nl') ? 'nl' : 'en') as 'nl' | 'en';
  const t = (nl: string, en: string) => (lang === 'nl' ? nl : en);
  const toast = useToast();

  // Admin-capability gate (R1.3 — UX ONLY; SAM enforces authoritatively). Source `user` from the
  // auth context and compute `members:admin` EXACTLY as `pages/MemberAnalyticsPage.tsx` does:
  // `Tenant_Admin` satisfies `members:admin`. A non-admin keeps the read-only list but loses the
  // create/edit/retire affordances (see the mutation gating below); the SAM 403 remains the real guard.
  const { user } = useAuth();
  const isMembersAdmin = (user?.roles ?? []).some((role) => MEMBERS_ADMIN_ROLES.includes(role));

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<MembershipType[]>([]);

  // Create/edit modal state (task 2.2). The manager owns the modal because it owns `entries` +
  // `load()` — the modal's `onMutated` refreshes this list (R2.6) and the modal then closes.
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<MembershipTypeModalMode>('create');
  const [editEntry, setEditEntry] = useState<MembershipType | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      // ALL entries incl. retired (NO active filter — R1.2). The service unwraps the
      // `{ data }` envelope; on failure it throws a structured ApiError we surface below.
      const data = await listMembershipTypes<MembershipType[]>();
      setEntries(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  const sorted = useMemo(() => sortCatalog(entries), [entries]);

  // Create (task 2.2): open the modal in create mode. A parent `onCreate` override wins if passed.
  // Gated on `members:admin` (task 2.4) as a defensive no-op — the create affordance is hidden for a
  // non-admin, so this guard only matters if a mutation path is reached some other way (SAM 403 anyway).
  const handleCreate = () => {
    if (!isMembersAdmin) return;
    if (onCreate) {
      onCreate();
      return;
    }
    setModalMode('create');
    setEditEntry(null);
    setModalOpen(true);
  };

  // Edit (task 2.2): row-click opens the edit modal pre-filled with the selected entry (looked up
  // by `type_code`). A parent `onEdit` override wins if passed (frontend row-click convention).
  // Gated on `members:admin` (task 2.4): a non-admin's row is not clickable (no handler wired below),
  // and this guard is a belt-and-suspenders no-op so the mutation modal never opens for a non-admin.
  const handleEdit = (typeCode: string) => {
    if (!isMembersAdmin) return;
    if (onEdit) {
      onEdit(typeCode);
      return;
    }
    const selected = entries.find((e) => codeOf(e) === typeCode) ?? null;
    setModalMode('edit');
    setEditEntry(selected);
    setModalOpen(true);
  };

  if (loading) {
    return (
      <Box p={4} data-testid="membership-types-loading">
        <Spinner color="orange.400" />
        <Text color="gray.400" display="inline" ml={2}>
          {t('Lidmaatschapstypes laden…', 'Loading membership types…')}
        </Text>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4}>
        <Text color="red.300" data-testid="membership-types-error">
          {error}
        </Text>
      </Box>
    );
  }

  return (
    <Box data-testid="membership-types-manager">
      <HStack justify="space-between" mb={3}>
        <Text fontSize="md" color="gray.200" fontWeight="semibold">
          {t('Lidmaatschapstypes', 'Membership types')}
        </Text>
        {/* Create action — HIDDEN (not just disabled) for a non-admin (R1.3, task 2.4). Absence is
            the stable signal task 2.5 asserts: a non-admin query for `membership-types-create` is null. */}
        {isMembersAdmin && (
          <Button
            size="sm"
            colorScheme="orange"
            onClick={handleCreate}
            data-testid="membership-types-create"
          >
            {t('Nieuw type', 'New type')}
          </Button>
        )}
      </HStack>

      {sorted.length === 0 ? (
        // Empty state (R1.4): friendly, bilingual, WITH a create action — never a crash.
        <VStack
          spacing={3}
          py={10}
          align="center"
          data-testid="membership-types-empty"
        >
          <Text color="gray.400" textAlign="center">
            {isMembersAdmin
              ? t(
                'Er zijn nog geen lidmaatschapstypes. Maak het eerste type aan om te beginnen.',
                'There are no membership types yet. Create the first type to get started.',
              )
              : t(
                'Er zijn nog geen lidmaatschapstypes.',
                'There are no membership types yet.',
              )}
          </Text>
          {/* Empty-state create — HIDDEN for a non-admin too (R1.3, task 2.4): the empty state stays a
              friendly read-only notice, with no mutation affordance for a caller lacking `members:admin`. */}
          {isMembersAdmin && (
            <Button
              colorScheme="orange"
              onClick={handleCreate}
              data-testid="membership-types-empty-create"
            >
              {t('Eerste type aanmaken', 'Create first type')}
            </Button>
          )}
        </VStack>
      ) : (
        <Table size="sm" variant="simple" data-testid="membership-types-table">
          <Thead>
            <Tr>
              <Th color="gray.400">{t('Code', 'Code')}</Th>
              <Th color="gray.400">{t('Label', 'Label')}</Th>
              <Th color="gray.400">{t('Status', 'Status')}</Th>
              <Th color="gray.400" isNumeric>
                {t('Volgorde', 'Order')}
              </Th>
            </Tr>
          </Thead>
          <Tbody>
            {sorted.map((entry) => {
              const code = codeOf(entry);
              const label = resolveFieldConfigLabel(entry.label, lang, code);
              const active = entry.active !== false;
              return (
                <Tr
                  key={code}
                  // Rows are a mutation affordance (row-click opens the edit/retire modal). For a
                  // non-admin (R1.3, task 2.4) the row is NON-mutating: no click handler, no pointer
                  // cursor, no hover highlight — the entry is still SHOWN (read-only), it just can't
                  // open the modal. SAM's 403 remains the authoritative guard if a write is attempted.
                  onClick={isMembersAdmin ? () => handleEdit(code) : undefined}
                  cursor={isMembersAdmin ? 'pointer' : 'default'}
                  _hover={isMembersAdmin ? { bg: 'gray.800' } : undefined}
                  data-testid={`membership-types-row-${code}`}
                >
                  <Td color="gray.200" fontFamily="mono">
                    {code}
                  </Td>
                  <Td color="gray.200">{label}</Td>
                  <Td>
                    <Badge colorScheme={active ? 'green' : 'gray'}>
                      {active ? t('Actief', 'Active') : t('Gepensioneerd', 'Retired')}
                    </Badge>
                  </Td>
                  <Td color="gray.300" isNumeric>
                    {typeof entry.order === 'number' ? entry.order : 0}
                  </Td>
                </Tr>
              );
            })}
          </Tbody>
        </Table>
      )}

      {/* Create/edit/retire modal (task 2.2). `onMutated` refreshes THIS list (R2.6) on success;
          the modal shows the success toast + closes itself. Only rendered when open so the form
          re-seeds cleanly on each open (create vs edit, and per selected entry). */}
      {modalOpen && (
        <MembershipTypeModal
          isOpen={modalOpen}
          mode={modalMode}
          entry={editEntry}
          lang={lang}
          canMutate={isMembersAdmin}
          onMutated={load}
          onClose={() => setModalOpen(false)}
        />
      )}
    </Box>
  );
};

export default MembershipTypesManager;
