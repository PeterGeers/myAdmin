/**
 * Members Overview — data-loading hook. Extracted from `pages/MembersPage.tsx`
 * during the file-length split (code-quality-fixes 2026-10-15, task 6) with ZERO
 * behaviour change: the state, effects, and handlers below are moved verbatim —
 * same order, same dependency arrays, same defensive `Promise.resolve(...)`
 * wrappers — so the page's observable load behaviour is identical.
 *
 * Owns: the members list, the resolved field config, the active membership-type
 * catalog, the loading flag, the user's chosen-column keys + per-user page-size
 * preference (seeded from the persisted column preferences), and the optimistic
 * column-save handler.
 */

import { useState, useEffect, useCallback } from 'react';
import { useToast } from '@chakra-ui/react';
import {
  listMembers, getFieldConfig, listMembershipTypes,
  getColumnPreferences, saveColumnPreferences,
} from '../../../services/membersApiService';
import { ALWAYS_ON_COLUMN_KEY } from '../ColumnChooser';
import type { Member, FieldConfig, MembershipType } from '../../../types/members';

export interface UseMembersDataReturn {
  members: Member[];
  fieldConfig: FieldConfig | null;
  membershipTypes: MembershipType[] | null;
  loading: boolean;
  chosenKeys: string[];
  userPageSize: number | null;
  loadMembers: () => Promise<void>;
  handleColumnsChange: (nextKeys: string[]) => void;
}

/**
 * @param t translation function (members namespace) — only used for toast copy.
 */
export function useMembersData(t: (key: string) => string): UseMembersDataReturn {
  const toast = useToast();

  const [members, setMembers] = useState<Member[]>([]);
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  // The tenant's ACTIVE Lidmaatschap Beheer catalog entries (R5.8), fetched via
  // listMembershipTypes(true). Feed the add/edit modals' membership_type dropdown with
  // active-only types; the domain re-validates the chosen type authoritatively.
  const [membershipTypes, setMembershipTypes] = useState<MembershipType[] | null>(null);
  const [loading, setLoading] = useState(true);

  // The user's own ordered chosen-column keys (session-columns R3.1). This is the
  // single source of which non-fixed columns show; member_number is implied +
  // pinned first by the model (R7), so it is never part of this list. Seeded on
  // mount from the persisted `getColumnPreferences()` once the field config
  // resolves (C8) — empty for a first-time user (R6.4).
  const [chosenKeys, setChosenKeys] = useState<string[]>([]);

  // The user's own per-user rows-per-page preference (Members config redesign
  // Phase 2, step (a) — the pagination re-home). Seeded from the SAME per-user
  // column/table preference record (`getColumnPreferences`) that seeds
  // `chosenKeys`, so it is the HIGHEST-precedence input to the page-size resolver
  // (`userPreference ?? default_page_size ?? platformDefault`, R2.3). `null` =
  // the user has no explicit preference → fall through to the tenant default.
  const [userPageSize, setUserPageSize] = useState<number | null>(null);

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
        // Seed the per-user page-size preference (R2.3). The resolver guards for
        // positivity, so a null/absent/non-positive stored value simply falls
        // through to the tenant default — pass it through verbatim here.
        setUserPageSize(
          typeof prefs.page_size === 'number' ? prefs.page_size : null,
        );
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

  return {
    members,
    fieldConfig,
    membershipTypes,
    loading,
    chosenKeys,
    userPageSize,
    loadMembers,
    handleColumnsChange,
  };
}
